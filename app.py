# -*- coding: utf-8 -*-
# Complete Free Fire API – Friend list directly from JWT, guest login, or access token
# Deployable to Vercel – no temporary files, no external proto files.

import sys
import json
import time
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request, jsonify
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from google.protobuf import json_format

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ============================================================================
# 1. Friend list fetcher (multi‑server, multi‑threaded)
# ============================================================================
FREEFIRE_VERSION = "OB53"
FRIEND_ENDPOINT = "/GetFriend"

FRIEND_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
FRIEND_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

SERVER_BASE_URLS = [
    "https://client.ind.freefiremobile.com",   # IND
    "https://clientbp.ggblueshark.com",        # ME, PK
    "https://clientbp.ggwhitehawk.com",        # BD
    "https://clientbp.ggpolarbear.com",        # VN, SG, ID, TH, RU
    "https://client.us.freefiremobile.com",    # BR, NA
]

# ----- Embedded Friends protobuf (fully self-contained) -----
# This is the compiled source of fr_list_pb2.py
_friends_pb2_src = '''
# -*- coding: utf-8 -*-
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\\n\\rFriends.proto\\"\\"\\n\\x06\\x46riend\\x12\\n\\n\\x02ID\\x18\\x01 \\x01(\\x03\\x12\\x0c\\n\\x04Name\\x18\\x03 \\x01(\\t\\"#\\n\\x07\\x46riends\\x12\\x18\\n\\x07\\x66ield_1\\x18\\x01 \\x03(\\x0b\\x32\\x07.Friendb\\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'Friends_pb2', _globals)
Friends = _globals['Friends']
'''
# Execute the source code to create the Friends class in this module's namespace
exec(_friends_pb2_src, globals())

def encrypt_friend_payload(hex_data: str) -> bytes:
    raw = bytes.fromhex(hex_data)
    cipher = AES.new(FRIEND_KEY, AES.MODE_CBC, FRIEND_IV)
    return cipher.encrypt(pad(raw, AES.block_size))

def parse_friend_response(content_bytes: bytes):
    pb = Friends()
    pb.ParseFromString(content_bytes)
    parsed = json.loads(json_format.MessageToJson(pb))
    raw_list = []
    for entry in parsed.get("field1", []):
        uid = str(entry.get("ID", "unknown"))
        name = entry.get("Name", "unknown")
        raw_list.append({"uid": uid, "name": name})
    if not raw_list:
        return None, None
    my_info = raw_list[-1]
    friends_list = raw_list[:-1]
    return friends_list, my_info

def fetch_from_server(base_url: str, jwt: str, timeout: int = 10):
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
        r = requests.post(url, headers=headers, data=encrypted_payload, timeout=timeout, verify=False)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        friends_list, my_info = parse_friend_response(r.content)
        if friends_list is None:
            return None, "Empty response"
        return (friends_list, my_info), None
    except Exception as e:
        return None, str(e)

def get_friend_list_from_jwt(jwt):
    """Return (friends_list, my_info) or (None, error_message)."""
    with ThreadPoolExecutor(max_workers=len(SERVER_BASE_URLS)) as executor:
        future_to_url = {executor.submit(fetch_from_server, url, jwt): url for url in SERVER_BASE_URLS}
        errors = []
        for future in as_completed(future_to_url):
            result, error = future.result()
            if result is not None:
                for f in future_to_url:
                    f.cancel()
                return result[0], result[1]
            errors.append(error)
    return None, f"All servers failed: {errors[:3]}"

# ============================================================================
# 2. Guest login (uid + password → JWT)
# ============================================================================
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
    'ReleaseVersion': "OB53"
}

# ----- Embedded MajorLoginReq and MajorLoginRes protobufs (compiled sources) -----
_major_login_req_pb2_src = '''
# -*- coding: utf-8 -*-
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
import base64
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(base64.b64decode("ChNNYWpvckxvZ2luUmVxLnByb3RvIvoKCgpNYWpvckxvZ2luEhIKCmV2ZW50X3RpbWUYAyABKAkSEQoJZ2FtZV9uYW1lGAQgASgJEhMKC3BsYXRmb3JtX2lkGAUgASgFEhYKDmNsaWVudF92ZXJzaW9uGAcgASgJEhcKD3N5c3RlbV9zb2Z0d2FyZRgIIAEoCRIXCg9zeXN0ZW1faGFyZHdhcmUYCSABKAkSGAoQdGVsZWNvbV9vcGVyYXRvchgKIAEoCRIUCgxuZXR3b3JrX3R5cGUYCyABKAkSFAoMc2NyZWVuX3dpZHRoGAwgASgNEhUKDXNjcmVlbl9oZWlnaHQYDSABKA0SEgoKc2NyZWVuX2RwaRgOIAEoCRIZChFwcm9jZXNzb3JfZGV0YWlscxgPIAEoCRIOCgZtZW1vcnkYECABKA0SFAoMZ3B1X3JlbmRlcmVyGBEgASgJEhMKC2dwdV92ZXJzaW9uGBIgASgJEhgKEHVuaXF1ZV9kZXZpY2VfaWQYEyABKAkSEQoJY2xpZW50X2lwGBQgASgJEhAKCGxhbmd1YWdlGBUgASgJEg8KB29wZW5faWQYFiABKAkSFAoMb3Blbl9pZF90eXBlGBcgASgJEhMKC2RldmljZV90eXBlGBggASgJEicKEG1lbW9yeV9hdmFpbGFibGUYGSABKAsyDS5HYW1lU2VjdXJpdHkSFAoMYWNjZXNzX3Rva2VuGB0gASgJEhcKD3BsYXRmb3JtX3Nka19pZBgeIAEoBRIaChJuZXR3b3JrX29wZXJhdG9yX2EYKSABKAkSFgoObmV0d29ya190eXBlX2EYKiABKAkSHAoUY2xpZW50X3VzaW5nX3ZlcnNpb24YOSABKAkSHgoWZXh0ZXJuYWxfc3RvcmFnZV90b3RhbBg8IAEoBRIiChpleHRlcm5hbF9zdG9yYWdlX2F2YWlsYWJsZRg9IAEoBRIeChhpbnRlcm5hbF9zdG9yYWdlX3RvdGFsGD4gASgFEiIKGmludGVybmFsX3N0b3JhZ2VfYXZhaWxhYmxlGD8gASgFEiMKG2dhbWVfZGlza19zdG9yYWdlX2F2YWlsYWJsZRhAIAEoBRIfChdnYW1lX2Rpc2tfc3RvcmFnZV90b3RhbBhBIAEoBRIlCh1leHRlcm5hbF9zZGNhcmRfYXZhaWxfc3RvcmFnZRhCIAEoBRIlCh1leHRlcm5hbF9zZGNhcmRfdG90YWxfc3RvcmFnZRhDIAEoBRIQCghsb2dpbl9ieRhJIAEoBRIUCgxsaWJyYXJ5X3BhdGgYSiABKAkSEgoKcmVnX2F2YXRhchhMIAEoBRIVCg1saWJyYXJ5X3Rva2VuGE0gASgJEhQKDGNoYW5uZWxfdHlwZRhOIAEoBRIQCghjcHVfdHlwZRhPIAEoBRIYChBjcHVfYXJjaGl0ZWN0dXJlGFEgASgJEhsKE2NsaWVudF92ZXJzaW9uX2NvZGUYUyABKAkSFAoMZ3JhcGhpY3NfYXBpGFYgASgJEh0KFXN1cHBvcnRlZF9hc3RjX2JpdHNldBhXIAEoDRIaChJsb2dpbl9vcGVuX2lkX3R5cGUYWCABKAUSGAoQYW5hbHl0aWNzX2RldGFpbBhZIAEoDBIUCgxsb2FkaW5nX3RpbWUYXCABKA0SFwoPcmVsZWFzZV9jaGFubmVsGF0gASgJEhIKCmV4dHJhX2luZm8YXiABKAkSIAoYYW5kcm9pZF9lbmdpbmVfaW5pdF9mbGFnGF8gASgNEg8KB2lmX3B1c2gYYSABKAUSDgoGaXNfdnBuGGIgASgFEhwKFG9yaWdpbl9wbGF0Zm9ybV90eXBlGGMgASgJEh0KFXByaW1hcnlfcGxhdGZvcm1fdHlwZRhkIAEoCSI1CgxHYW1lU2VjdXJpdHkSDwoHdmVyc2lvbhgGIAEoBRIUCgxoaWRkZW5fdmFsdWUYCCABKARiBnByb3RvMw=="))
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'MajorLoginReq_pb2', _globals)
MajorLogin = _globals['MajorLogin']
GameSecurity = _globals['GameSecurity']
'''
_major_login_res_pb2_src = '''
# -*- coding: utf-8 -*-
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
import base64
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(base64.b64decode("ChNNYWpvckxvZ2luUmVzLnByb3RvInwKDU1ham9yTG9naW5SZXMSEwoLYWNjb3VudF91aWQYASABKAQSDgoGcmVnaW9uGAIgASgJEg0KBXRva2VuGAggASgJEgsKA3VybBgKIAEoCRIRCgl0aW1lc3RhbXAYFSABKAMSCwoDa2V5GBYgASgMEgoKAml2GBcgASgMYgZwcm90bzM="))
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'MajorLoginRes_pb2', _globals)
MajorLoginRes = _globals['MajorLoginRes']
'''
# Execute both to make the classes available
exec(_major_login_req_pb2_src, globals())
exec(_major_login_res_pb2_src, globals())

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
    msg = MajorLogin()
    # Basic fields
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
    # memory_available sub-message
    if hasattr(msg, 'memory_available'):
        msg.memory_available.version = 55
        msg.memory_available.hidden_value = 81
    msg.access_token = access_token
    msg.platform_sdk_id = 1
    msg.network_operator_a = "Verizon"
    msg.network_type_a = "WIFI"
    msg.client_using_version = "7428b253defc164018c604a1ebbfebdf"
    # Optional storage fields (set only if they exist)
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
        resp = requests.post(OAUTH_URL, headers=headers, data=data, timeout=30, verify=False)
        if resp.status_code == 200:
            j = resp.json()
            return j.get("open_id"), j.get("access_token"), None
        return None, None, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return None, None, str(e)

def major_login(open_id, access_token, platform_type=4):
    proto_payload = build_major_login_message(open_id, access_token, platform_type)
    encrypted = encrypt_proto(proto_payload)
    try:
        resp = requests.post(MAJOR_LOGIN_URL, data=encrypted, headers=BASE_HEADERS, timeout=30, verify=False)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        data = resp.content
        # Try decryption first
        if len(data) % 16 == 0:
            dec = decrypt_proto(data)
            if dec:
                res = MajorLoginRes()
                res.ParseFromString(dec)
                if res.token:
                    return True, {'token': res.token, 'account_uid': res.account_uid, 'region': res.region, 'url': res.url}
        # Fallback: parse directly
        res = MajorLoginRes()
        res.ParseFromString(data)
        if res.token:
            return True, {'token': res.token, 'account_uid': res.account_uid, 'region': res.region, 'url': res.url}
        return False, "No token in response"
    except Exception as e:
        return False, str(e)

def get_jwt_from_guest(uid, password):
    open_id, access_token, err = generate_access_token(uid, password)
    if err:
        return None, f"Token generation failed: {err}"
    # Try multiple platform types
    for pt in [2, 3, 4, 6, 8]:
        success, login_data = major_login(open_id, access_token, pt)
        if success:
            return login_data['token'], None
    return None, "All platform types failed in MajorLogin"

def get_jwt_from_access_token(access_token):
    inspect_url = f"https://100067.connect.garena.com/oauth/token/inspect?token={access_token}"
    try:
        resp = requests.get(inspect_url, timeout=10)
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
    return None, "All platform types failed for access token"

# ============================================================================
# 3. Flask Routes – all return friend list directly
# ============================================================================
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
        return jsonify({"status": "error", "message": "ERROR UNABLE TO FIND LIST", "details": my_info}), 500
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
        return jsonify({"status": "error", "message": "Friend list fetch failed", "details": my_info}), 500
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
    access_token = request.args.get('access_token')
    if not access_token:
        return jsonify({"status": "error", "message": "Missing access_token"}), 400
    jwt, err = get_jwt_from_access_token(access_token)
    if err:
        return jsonify({"status": "error", "message": err}), 401
    friends, my_info = get_friend_list_from_jwt(jwt)
    if friends is None:
        return jsonify({"status": "error", "message": "Friend list fetch failed", "details": my_info}), 500
    return jsonify({
        "status": "success",
        "friends_count": len(friends),
        "friends_list": friends,
        "my_info": my_info,
        "Credit": "RIZER",
        "timestamp": int(time.time())
    })

# For local development
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
