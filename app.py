# -*- coding: utf-8 -*-
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request, jsonify
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from google.protobuf import json_format

import fr_list_pb2
import major_login_req_pb2
import major_login_res_pb2

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ========== Constants ==========
FREEFIRE_VERSION = "OB53"
FRIEND_ENDPOINT = "/GetFriend"
FRIEND_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
FRIEND_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

SERVER_BASE_URLS = [
    "https://client.ind.freefiremobile.com",
    "https://clientbp.ggblueshark.com",
    "https://clientbp.ggwhitehawk.com",
    "https://clientbp.ggpolarbear.com",
    "https://client.us.freefiremobile.com",
]

# Login endpoints & keys
OAUTH_URL = "https://100067.connect.garena.com/oauth/guest/token/grant"
MAJOR_LOGIN_URL = "https://loginbp.ggblueshark.com/MajorLogin"
CLIENT_ID = "100067"
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
PROTO_KEY = b'Yg&tc%DEuh6%Zc^8'
PROTO_IV = b'6oyZDr22E3ychjM%'
BASE_HEADERS = {
    'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
    'Connection': "Keep-Alive",
    'Accept-Encoding': "gzip",
    'Content-Type': "application/x-www-form-urlencoded",
    'Expect': "100-continue",
    'X-Unity-Version': "2018.4.11f1",
    'X-GA': "v1 1",
    'ReleaseVersion': FREEFIRE_VERSION,
}

# ========== Friend list helpers ==========
def encrypt_friend_payload(hex_data: str) -> bytes:
    raw = bytes.fromhex(hex_data)
    cipher = AES.new(FRIEND_KEY, AES.MODE_CBC, FRIEND_IV)
    return cipher.encrypt(pad(raw, AES.block_size))

def parse_friend_response(content_bytes: bytes):
    pb = fr_list_pb2.Friends()
    pb.ParseFromString(content_bytes)
    parsed = json.loads(json_format.MessageToJson(pb))
    raw_list = []
    for entry in parsed.get("field1", []):
        uid = str(entry.get("ID", "unknown"))
        name = entry.get("Name", "unknown")
        raw_list.append({"uid": uid, "name": name})
    if not raw_list:
        return None, None
    return raw_list[:-1], raw_list[-1]   # friends, my_info

def fetch_from_server(base_url: str, jwt: str, timeout: int = 8):
    url = f"{base_url}{FRIEND_ENDPOINT}"
    headers = {
        "Expect": "100-continue",
        "Authorization": f"Bearer {jwt}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": FREEFIRE_VERSION,
        "Content-Type": "application/octet-stream",
        "User-Agent": "Dalvik/2.1.0 (Linux; Android 11)",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    payload_hex = "080110011001"
    encrypted_payload = encrypt_friend_payload(payload_hex)
    try:
        r = requests.post(url, headers=headers, data=encrypted_payload,
                          timeout=timeout, verify=False)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        friends, me = parse_friend_response(r.content)
        if friends is None:
            return None, "Empty response"
        return (friends, me), None
    except Exception as e:
        return None, str(e)

def get_friend_list_from_jwt(jwt):
    # Limit threads to 3 to avoid overloading serverless environment
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_from_server, url, jwt): url for url in SERVER_BASE_URLS}
        errors = []
        for future in as_completed(futures):
            result, error = future.result()
            if result is not None:
                # cancel remaining futures (best effort)
                for f in futures:
                    f.cancel()
                return result[0], result[1]
            errors.append(error)
    return None, f"All servers failed: {errors[:3]}"

# ========== Login helpers ==========
def encrypt_proto(payload_bytes):
    cipher = AES.new(PROTO_KEY, AES.MODE_CBC, PROTO_IV)
    return cipher.encrypt(pad(payload_bytes, AES.block_size))

def decrypt_proto(encrypted_bytes):
    try:
        cipher = AES.new(PROTO_KEY, AES.MODE_CBC, PROTO_IV)
        return unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
    except:
        return None

def build_major_login_message(open_id, access_token, platform_type=4):
    msg = major_login_req_pb2.MajorLogin()
    msg.event_time = str(datetime.now())[:-7]
    msg.game_name = "free fire"
    msg.platform_id = 1
    msg.client_version = "1.123.1"
    msg.system_software = "Android OS 9 / API-28 (PQ3B.190801.10101846/G9650ZHU2ARC6)"
    msg.system_hardware = "Handheld"
    msg.telecom_operator = "Verizon"
    msg.network_type = "WIFI"
    msg.screen_width = 1920
    msg.screen_height = 1080
    msg.screen_dpi = "280"
    msg.processor_details = "ARM64 FP ASIMD AES VMH | 2865 | 4"
    msg.memory = 3003
    msg.gpu_renderer = "Adreno (TM) 640"
    msg.gpu_version = "OpenGL ES 3.1 v1.46"
    msg.unique_device_id = "Google|34a7dcdf-a7d5-4cb6-8d7e-3b0e448a0c57"
    msg.client_ip = "223.191.51.89"
    msg.language = "en"
    msg.open_id = open_id
    msg.open_id_type = "4"
    msg.device_type = "Handheld"
    if hasattr(msg, 'memory_available'):
        msg.memory_available.version = 55
        msg.memory_available.hidden_value = 81
    msg.access_token = access_token
    msg.platform_sdk_id = 1
    msg.network_operator_a = "Verizon"
    msg.network_type_a = "WIFI"
    msg.client_using_version = "7428b253defc164018c604a1ebbfebdf"

    # Optional fields (safe set)
    optional_fields = [
        ('external_storage_total', 36235),
        ('external_storage_available', 31335),
        ('internal_storage_total', 2519),
        ('internal_storage_available', 703),
        ('game_disk_storage_available', 25010),
        ('game_disk_storage_total', 26628),
        ('external_sdcard_avail_storage', 32992),
        ('external_sdcard_total_storage', 36235),
    ]
    for attr, val in optional_fields:
        if hasattr(msg, attr):
            setattr(msg, attr, val)

    msg.login_by = 3
    msg.library_path = "/data/app/com.dts.freefireth-YPKM8jHEwAJlhpmhDhv5MQ==/lib/arm64"
    msg.reg_avatar = 1
    msg.library_token = "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-YPKM8jHEwAJlhpmhDhv5MQ==/base.apk"
    msg.channel_type = 3
    msg.cpu_type = 2
    msg.cpu_architecture = "64"
    msg.client_version_code = "2019118695"
    msg.graphics_api = "OpenGLES2"
    msg.supported_astc_bitset = 16383
    msg.login_open_id_type = 4
    msg.analytics_detail = b"FwQVTgUPX1UaUllDDwcWCRBpWA0FUgsvA1snWlBaO1kFYg=="
    msg.loading_time = 13564
    msg.release_channel = "android"
    msg.extra_info = "KqsHTymw5/5GB23YGniUYN2/q47GATrq7eFeRatf0NkwLKEMQ0PK5BKEk72dPflAxUlEBir6Vtey83XqF593qsl8hwY="
    msg.android_engine_init_flag = 110009
    msg.if_push = 1
    msg.is_vpn = 1
    msg.origin_platform_type = str(platform_type)
    msg.primary_platform_type = str(platform_type)
    return msg.SerializeToString()

def generate_access_token(uid, password):
    headers = {
        "Host": "100067.connect.garena.com",
        "User-Agent": "GarenaMSDK/5.5.2P3(SM-A515F;Android 12;en-US;IND;)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "close"
    }
    data = {
        "uid": uid, "password": password, "response_type": "token",
        "client_type": "2", "client_secret": CLIENT_SECRET, "client_id": CLIENT_ID
    }
    try:
        resp = requests.post(OAUTH_URL, headers=headers, data=data,
                             timeout=15, verify=False)
        if resp.status_code == 200:
            j = resp.json()
            return j.get("open_id"), j.get("access_token"), None
        return None, None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, None, str(e)

def major_login(open_id, access_token, platform_type=4):
    proto_payload = build_major_login_message(open_id, access_token, platform_type)
    encrypted = encrypt_proto(proto_payload)
    try:
        resp = requests.post(MAJOR_LOGIN_URL, data=encrypted, headers=BASE_HEADERS,
                             timeout=15, verify=False)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        data = resp.content
        # Try decryption first
        if len(data) % 16 == 0:
            dec = decrypt_proto(data)
            if dec:
                res = major_login_res_pb2.MajorLoginRes()
                res.ParseFromString(dec)
                if res.token:
                    return True, {'token': res.token}
        # Fallback: parse directly
        res = major_login_res_pb2.MajorLoginRes()
        res.ParseFromString(data)
        if res.token:
            return True, {'token': res.token}
        return False, "No token"
    except Exception as e:
        return False, str(e)

def get_jwt_from_guest(uid, password):
    open_id, access_token, err = generate_access_token(uid, password)
    if err:
        return None, f"Token generation failed: {err}"
    for pt in [2, 3, 4, 6, 8]:
        success, login_data = major_login(open_id, access_token, pt)
        if success:
            return login_data['token'], None
    return None, "All platform types failed"

def get_jwt_from_access_token(access_token):
    inspect_url = f"https://100067.connect.garena.com/oauth/token/inspect?token={access_token}"
    try:
        resp = requests.get(inspect_url, timeout=10, verify=False)
        if resp.status_code != 200:
            return None, f"Inspect failed: HTTP {resp.status_code}"
        data = resp.json()
        open_id = data.get('open_id')
        if not open_id:
            return None, "open_id not found"
    except Exception as e:
        return None, str(e)
    for pt in [2, 3, 4, 6, 8]:
        success, login_data = major_login(open_id, access_token, pt)
        if success:
            return login_data['token'], None
    return None, "All platform types failed"

# ========== Flask Routes ==========
@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "endpoints": {
            "jwt": "/<JWT>",
            "guest": "/guest?uid=<uid>&password=<password>",
            "access_token": "/access_token?access_token=<access_token>"
        }
    })

@app.route("/<path:jwt>", methods=["GET"])
def friend_list_from_jwt(jwt):
    if not jwt or jwt.count(".") != 2:
        return jsonify({"status": "error", "message": "Invalid JWT"}), 400
    friends, my_info = get_friend_list_from_jwt(jwt)
    if friends is None:
        return jsonify({"status": "error", "message": "ERROR UNABLE TO FIND LIST",
                        "details": my_info}), 500
    return jsonify({
        "status": "success",
        "friends_count": len(friends),
        "friends_list": friends,
        "my_info": my_info,
        "Credit": "RIZER",
        "timestamp": int(time.time())
    })

@app.route("/guest", methods=["GET"])
def guest_login():
    uid = request.args.get('uid')
    password = request.args.get('password')
    if not uid or not password:
        return jsonify({"status": "error", "message": "Missing uid or password"}), 400
    jwt, err = get_jwt_from_guest(uid, password)
    if err:
        return jsonify({"status": "error", "message": err}), 401
    friends, my_info = get_friend_list_from_jwt(jwt)
    if friends is None:
        return jsonify({"status": "error", "message": "Friend list fetch failed",
                        "details": my_info}), 500
    return jsonify({
        "status": "success",
        "friends_count": len(friends),
        "friends_list": friends,
        "my_info": my_info,
        "Credit": "RIZER",
        "timestamp": int(time.time())
    })

@app.route("/access_token", methods=["GET"])
def access_token_login():
    token = request.args.get('access_token')
    if not token:
        return jsonify({"status": "error", "message": "Missing access_token"}), 400
    jwt, err = get_jwt_from_access_token(token)
    if err:
        return jsonify({"status": "error", "message": err}), 401
    friends, my_info = get_friend_list_from_jwt(jwt)
    if friends is None:
        return jsonify({"status": "error", "message": "Friend list fetch failed",
                        "details": my_info}), 500
    return jsonify({
        "status": "success",
        "friends_count": len(friends),
        "friends_list": friends,
        "my_info": my_info,
        "Credit": "RIZER",
        "timestamp": int(time.time())
    })