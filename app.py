import requests
import json
import urllib3
import base64
import gzip
import zlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from google.protobuf import json_format
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
from flask import Flask, request, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------- Protobuf definitions (from xPB2.py) -------------------------
_sym_db = _symbol_database.Default()

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\rFriends.proto\"\"\n\x06\x46riend\x12\n\n\x02ID\x18\x01 \x01(\x03\x12\x0c\n\x04Name\x18\x03 \x01(\t\"#\n\x07\x46riends\x12\x18\n\x07\x66ield_1\x18\x01 \x03(\x0b\x32\x07.Friendb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'Friends_pb2', _globals)
if _descriptor_pool._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _globals['_FRIEND'] = DESCRIPTOR.message_types_by_name['Friend']
    _globals['_FRIENDS'] = DESCRIPTOR.message_types_by_name['Friends']

# Import the generated classes into the current namespace
Friends = _globals.get('Friends')
Friend = _globals.get('Friend')
if Friends is None or Friend is None:
    # fallback: define simple classes (should not happen, but just in case)
    class Friend:
        pass
    class Friends:
        pass
# -------------------------------------------------------------------------------------

# Constants
KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

# Region to server URL mapping
REGION_SERVERS = {
    "IND": "https://client.ind.freefiremobile.com",
    "ME": "https://clientbp.ggblueshark.com",
    "VN": "https://clientbp.ggpolarbear.com",
    "BD": "https://clientbp.ggwhitehawk.com",
    "PK": "https://clientbp.ggblueshark.com",
    "SG": "https://clientbp.ggpolarbear.com",
    "BR": "https://client.us.freefiremobile.com",
    "NA": "https://client.us.freefiremobile.com",
    "ID": "https://clientbp.ggpolarbear.com",
    "RU": "https://clientbp.ggpolarbear.com",
    "TH": "https://clientbp.ggpolarbear.com"
}

# Default fallback server (if primary fails)
FALLBACK_SERVER = "https://clientbp.ggblueshark.com"

# External API endpoints
JWT_FROM_ACCESS_TOKEN_URL = "https://rizerxaccessjwt.vercel.app/rizer"
JWT_FROM_GUEST_URL = "https://rizerxguestaccountacceee.vercel.app/rizer"

# ================== Encryption / Protobuf Helpers ==================
def encrypt_aes(hex_data):
    try:
        cipher = AES.new(KEY, AES.MODE_CBC, IV)
        return cipher.encrypt(pad(bytes.fromhex(hex_data), AES.block_size)).hex()
    except Exception as e:
        raise Exception(f"Encryption failed: {str(e)}")

def decrypt_aes(encrypted_bytes):
    try:
        if len(encrypted_bytes) % 16 != 0:
            return None
        cipher = AES.new(KEY, AES.MODE_CBC, IV)
        decrypted = cipher.decrypt(encrypted_bytes)
        try:
            decrypted = unpad(decrypted, AES.block_size)
        except:
            pass
        return decrypted
    except Exception as e:
        return None

def encode_varint(n):
    result = []
    while n:
        result.append((n & 0x7F) | (0x80 if n > 0x7F else 0))
        n >>= 7
    return bytes(result) if result else b'\x00'

def create_varint(field_number, value):
    field_header = (field_number << 3) | 0
    return encode_varint(field_header) + encode_varint(value)

def create_length_delimited(field_number, value):
    field_header = (field_number << 3) | 2
    encoded_value = value.encode() if isinstance(value, str) else value
    return encode_varint(field_header) + encode_varint(len(encoded_value)) + encoded_value

def create_protobuf(fields):
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, dict):
            nested_packet = create_protobuf(value)
            packet.extend(create_length_delimited(field, nested_packet))
        elif isinstance(value, int):
            packet.extend(create_varint(field, value))
        elif isinstance(value, str) or isinstance(value, bytes):
            packet.extend(create_length_delimited(field, value))
    return packet

def get_friends_with_jwt(jwt_token, server_url=None):
    """
    Attempt to get friends list using the provided JWT token.
    If server_url is provided, use it; otherwise auto-detect from region.
    """
    try:
        if not jwt_token:
            return {"status": "error", "message": "JWT token is required"}

        # If no server_url given, try to detect region from JWT payload
        if not server_url:
            region = detect_region_from_jwt(jwt_token)
            if region and region in REGION_SERVERS:
                server_url = REGION_SERVERS[region]
            else:
                server_url = REGION_SERVERS.get("VN")  # default

        url = f"{server_url}/GetFriend"

        payload = {1: 1, 2: 1, 7: 1}
        protobuf_data = create_protobuf(payload)
        encrypted = encrypt_aes(protobuf_data.hex())

        headers = {
            'Host': server_url.replace('https://', ''),
            'User-Agent': 'UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
            'Accept': '*/*',
            'Accept-Encoding': 'deflate, gzip',
            'Authorization': f'Bearer {jwt_token}',
            'X-GA': 'v1 1',
            'ReleaseVersion': 'OB53',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Unity-Version': '2022.3.47f1'
        }

        session = requests.Session()
        response = session.post(url, headers=headers, data=bytes.fromhex(encrypted), verify=False, timeout=15)

        if response.status_code == 401:
            return {"status": "error", "message": "Invalid or expired JWT token"}

        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Request failed with status {response.status_code}",
                "response_text": response.text[:500] if response.text else "Empty response"
            }

        response_data = response.content
        decrypted = decrypt_aes(response_data)

        if decrypted is None:
            # try decompression if needed
            try:
                if response.headers.get('Content-Encoding') == 'gzip':
                    response_data = gzip.decompress(response_data)
                elif response.headers.get('Content-Encoding') == 'deflate':
                    response_data = zlib.decompress(response_data)
            except:
                pass

            try:
                friends = Friends()
                friends.ParseFromString(response_data)
                friends_json = json.loads(json_format.MessageToJson(friends))

                result = []
                for friend in friends_json.get("field1", []):
                    result.append({
                        "uid": str(friend.get("ID", "unknown")),
                        "name": friend.get("Name", "unknown")
                    })

                return {
                    "status": "success",
                    "data": result,
                    "total": len(result),
                    "message": f"Successfully retrieved {len(result)} friends"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to parse protobuf: {str(e)}",
                    "raw_response_hex": response_data[:200].hex() if len(response_data) > 0 else "empty",
                    "raw_response_length": len(response_data)
                }
        else:
            try:
                friends = Friends()
                friends.ParseFromString(decrypted)
                friends_json = json.loads(json_format.MessageToJson(friends))

                result = []
                for friend in friends_json.get("field1", []):
                    result.append({
                        "uid": str(friend.get("ID", "unknown")),
                        "name": friend.get("Name", "unknown")
                    })

                return {
                    "status": "success",
                    "data": result,
                    "total": len(result),
                    "message": f"Successfully retrieved {len(result)} friends"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to parse protobuf: {str(e)}",
                    "decrypted_hex": decrypted[:200].hex() if decrypted else "empty"
                }

    except Exception as e:
        return {"status": "error", "message": str(e)}

def decode_jwt_payload(jwt_token):
    try:
        parts = jwt_token.split('.')
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except:
        return None

def detect_region_from_jwt(jwt_token):
    """Try to extract region from JWT payload."""
    payload = decode_jwt_payload(jwt_token)
    if not payload:
        return None
    # Common field names for region/country
    for field in ['region', 'country', 'lock_region', 'noti_region']:
        if field in payload:
            region_code = payload[field]
            if isinstance(region_code, str) and region_code.upper() in REGION_SERVERS:
                return region_code.upper()
    return None

# ================== External API Helpers ==================
def get_jwt_from_access_token(access_token):
    """Call external API to get JWT from access token."""
    try:
        params = {'access_token': access_token}
        response = requests.get(JWT_FROM_ACCESS_TOKEN_URL, params=params, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": f"Access token API returned {response.status_code}"}
        data = response.json()
        if not data.get('success'):
            return {"status": "error", "message": "Access token API returned failure", "details": data}
        jwt = data.get('jwt')
        if not jwt:
            return {"status": "error", "message": "No JWT in access token response"}
        # Extract region from response
        region = data.get('region')
        return {"status": "success", "jwt": jwt, "region": region}
    except Exception as e:
        return {"status": "error", "message": f"Access token request failed: {str(e)}"}

def get_jwt_from_guest(uid, password):
    """Call external API to get JWT from guest uid/password."""
    try:
        params = {'uid': uid, 'password': password}
        response = requests.get(JWT_FROM_GUEST_URL, params=params, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": f"Guest API returned {response.status_code}"}
        data = response.json()
        if data.get('status') != 'success':
            return {"status": "error", "message": "Guest API returned failure", "details": data}
        jwt = data.get('jwt_token')
        if not jwt:
            return {"status": "error", "message": "No JWT in guest response"}
        region = data.get('region')
        return {"status": "success", "jwt": jwt, "region": region}
    except Exception as e:
        return {"status": "error", "message": f"Guest request failed: {str(e)}"}

# ================== Flask App ==================
app = Flask(__name__)

@app.route('/rizer', methods=['GET'])
def rizer():
    # Check which parameters are present
    jwt_token = request.args.get('jwt_token')
    access_token = request.args.get('access_token')
    uid = request.args.get('uid')
    password = request.args.get('pass')

    # Prefer jwt_token if given
    if jwt_token:
        return get_friends_response(jwt_token)

    # Handle access_token
    if access_token:
        result = get_jwt_from_access_token(access_token)
        if result['status'] != 'success':
            return jsonify(result)
        jwt = result['jwt']
        region = result.get('region')
        # Use region if provided, otherwise auto-detect
        server_url = REGION_SERVERS.get(region) if region else None
        friends_result = get_friends_with_jwt(jwt, server_url)
        # Add metadata
        if friends_result.get('status') == 'success':
            friends_result['source'] = 'access_token'
            friends_result['original_region'] = region
        return jsonify(friends_result)

    # Handle guest login
    if uid and password:
        result = get_jwt_from_guest(uid, password)
        if result['status'] != 'success':
            return jsonify(result)
        jwt = result['jwt']
        region = result.get('region')
        server_url = REGION_SERVERS.get(region) if region else None
        friends_result = get_friends_with_jwt(jwt, server_url)
        if friends_result.get('status') == 'success':
            friends_result['source'] = 'guest'
            friends_result['original_region'] = region
        return jsonify(friends_result)

    # No valid parameters
    return jsonify({
        "status": "error",
        "message": "Missing required parameters. Use one of: jwt_token, access_token, or (uid and pass)"
    }), 400

def get_friends_response(jwt_token):
    """Helper to get friends from JWT with fallback."""
    region = detect_region_from_jwt(jwt_token)
    if region and region in REGION_SERVERS:
        server_url = REGION_SERVERS[region]
    else:
        server_url = None
    result = get_friends_with_jwt(jwt_token, server_url)
    # If primary fails, try fallback
    if result.get('status') == 'error' and server_url != FALLBACK_SERVER:
        fallback_result = get_friends_with_jwt(jwt_token, FALLBACK_SERVER)
        if fallback_result.get('status') == 'success':
            result = fallback_result
            result['fallback_used'] = True
    return jsonify(result)

# For local development
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
