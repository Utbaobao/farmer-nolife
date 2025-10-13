import json
import sys
import random
import time
from datetime import datetime
from http.client import HTTPSConnection
import threading
from concurrent.futures import ThreadPoolExecutor
from websocket import WebSocket, WebSocketConnectionClosedException

INFO_FILE = "info.txt"  # channel_url\nchannel_id\nguild_id\nvoice_channel_id\ndelay_between_messages\nsleep_time
TOKENS_FILE = "tokens.txt"
MESSAGES_FILE = "messages.txt"

def get_timestamp():
    return "[" + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + "]"

def random_sleep(duration, min_random, max_random):
    sleep_duration = duration + random.randint(min_random, max_random)
    print(f"{get_timestamp()} Sleeping for {sleep_duration} seconds")
    time.sleep(sleep_duration)

def read_info():
    try:
        with open(INFO_FILE, "r") as file:
            lines = [line.strip() for line in file.read().splitlines() if line.strip()]
            if len(lines) >= 6:
                return lines[0], lines[1], lines[2], lines[3], int(lines[4]), int(lines[5])
            else:
                print(f"{get_timestamp()} info.txt needs exactly 6 lines.")
                return None
    except FileNotFoundError:
        print(f"{get_timestamp()} Info file not found.")
        return None
    except ValueError:
        print(f"{get_timestamp()} Delays/sleep must be integers in info.txt.")
        return None

def write_info(channel_url, channel_id, guild_id, voice_channel_id, delay_between_messages, sleep_time):
    try:
        with open(INFO_FILE, "w") as file:
            file.write(f"{channel_url}\n{channel_id}\n{guild_id}\n{voice_channel_id}\n{delay_between_messages}\n{sleep_time}")
        print(f"{get_timestamp()} Written config to info.txt!")
    except Exception as e:
        print(f"{get_timestamp()} Error writing info: {e}")
        sys.exit(1)

def configure_info():
    try:
        channel_url = input("Text channel URL: ")
        channel_id = input("Text channel ID: ")
        guild_id = input("Guild ID: ")
        voice_channel_id = input("Voice channel ID: ")
        delay_between_messages = 1  # Set to 1 second as requested
        sleep_time = int(input("Default sleep time (seconds) after full cycle: "))
        write_info(channel_url, channel_id, guild_id, voice_channel_id, delay_between_messages, sleep_time)
    except Exception as e:
        print(f"{get_timestamp()} Error configuring: {e}")
        sys.exit(1)

def set_channel():
    info = read_info()
    if not info:
        configure_info()
        return
    channel_url, channel_id, guild_id, voice_channel_id, delay_between_messages, sleep_time = info
    new_url = input(f"Text channel URL (current: {channel_url}): ").strip() or channel_url
    new_cid = input(f"Text channel ID (current: {channel_id}): ").strip() or channel_id
    new_gid = input(f"Guild ID (current: {guild_id}): ").strip() or guild_id
    new_vid = input(f"Voice channel ID (current: {voice_channel_id}): ").strip() or voice_channel_id
    write_info(new_url, new_cid, new_gid, new_vid, 1, sleep_time)  # Update delay to 1

def show_help():
    print("Usage: python main.py [--config | --setC | --serial | --help]")
    print("--serial: Send messages sequentially (safer on mobile)")

# Messenger Functions
def get_connection():
    return HTTPSConnection("discord.com", 443)

def send_message(token, channel_id, message):
    print(f"{get_timestamp()} Attempting to send '{message[:20]}...' with token {token[:10]}...")
    conn = get_connection()
    super_props = json.dumps({
        "os": "Android", "browser": "Chrome Mobile", "device": "", "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "browser_version": "124.0.0.0", "os_version": "10", "referrer": "", "referring_domain": "",
        "referrer_current": "", "release_channel": "stable", "client_build_number": 999999,
        "client_event_source": None
    }).encode('utf-8').decode('latin1')
    header_data = {
        "Content-Type": "application/json",
        "Authorization": token,
        "X-Super-Properties": super_props,
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Mobile Safari/537.36",
        "X-Context-Properties": json.dumps({"location_guild_id": "", "location_channel_id": channel_id, "location_channel_type": 0})
    }
    message_data = json.dumps({"content": message, "tts": False, "nonce": str(int(time.time() * 1000))})
    try:
        conn.request("POST", f"/api/v10/channels/{channel_id}/messages", body=message_data, headers=header_data)
        resp = conn.getresponse()
        status = resp.status
        response_body = resp.read().decode('utf-8') if status != 204 else ""
        if 199 < status < 300:
            print(f"{get_timestamp()} SUCCESS: Message sent with {token[:10]}! Status {status}")
            return True
        else:
            print(f"{get_timestamp()} FAILED ({status}): {response_body} for {token[:10]}...")
            if status == 401:
                print("  -> Invalid token!")
            elif status == 403:
                print("  -> No permission.")
            elif status == 429:
                print("  -> Rate limited. WARNING: 1s delay is too low!")
            return False
    except Exception as e:
        print(f"{get_timestamp()} EXCEPTION: {e} for {token[:10]}...")
        return False
    finally:
        conn.close()

def load_messages():
    try:
        with open(MESSAGES_FILE, "r") as file:
            msgs = [line.strip() for line in file.read().splitlines() if line.strip()]
            print(f"{get_timestamp()} Loaded {len(msgs)} messages.")
            return msgs
    except FileNotFoundError:
        print(f"{get_timestamp()} messages.txt not found!")
        return []

def load_tokens():
    try:
        with open(TOKENS_FILE, "r") as file:
            toks = [line.strip() for line in file.read().splitlines() if line.strip()]
            print(f"{get_timestamp()} Loaded {len(toks)} tokens.")
            return toks
    except FileNotFoundError:
        print(f"{get_timestamp()} tokens.txt not found!")
        return []

def messenger_worker(token, channel_id, messages, delay_between_messages):
    print(f"{get_timestamp()} Worker for {token[:10]}...")
    for i, message in enumerate(messages, 1):
        print(f"{get_timestamp()} Sending msg {i}/{len(messages)}...")
        success = send_message(token, channel_id, message)
        if success:
            random_sleep(delay_between_messages, 0, 0)  # No random for 1s
        else:
            time.sleep(10)  # Backoff

# VC Functions (unchanged)
def vc_run(token, guild_id, voice_channel_id):
    sequence = [None]
    session_id = [None]
    resume_gateway_url = [None]
    heartbeat_acked = [True]
    
    def heartbeat_loop(ws, interval, stopper):
        jitter = 0.9
        while not stopper.wait(jitter * interval):
            if not heartbeat_acked[0]:
                raise WebSocketConnectionClosedException("Missed ACK")
            try:
                heartbeat_acked[0] = False
                ws.send(json.dumps({"op": 1, "d": sequence[0]}))
            except:
                raise WebSocketConnectionClosedException("HB fail")
            jitter = 1.0

    while True:
        ws = None
        stopper = threading.Event()
        try:
            ws = WebSocket()
            connect_url = resume_gateway_url[0] or "wss://gateway.discord.gg/?v=10&encoding=json"
            ws.connect(connect_url)
            print(f"{get_timestamp()} VC Connected: {token[:10]}...")
            
            while True:
                message = ws.recv()
                if not message:
                    raise WebSocketConnectionClosedException("Closed")
                data = json.loads(message)
                op = data.get('op')
                d = data.get('d', {})
                s = data.get('s')
                if s is not None:
                    sequence[0] = s
                
                if op == 10:
                    interval = d['heartbeat_interval'] / 1000
                    hb_thread = threading.Thread(target=heartbeat_loop, args=(ws, interval, stopper))
                    hb_thread.daemon = True
                    hb_thread.start()
                    if session_id[0]:
                        ws.send(json.dumps({"op": 6, "d": {"token": token, "session_id": session_id[0], "seq": sequence[0]}}))
                    else:
                        ws.send(json.dumps({
                            "op": 2, "d": {"token": token, "properties": {"$os": "android", "$browser": "chrome", "$device": "mobile"}, "intents": 513}
                        }))
                
                elif op == 0:
                    t = data.get('t')
                    if t == 'READY':
                        session_id[0] = d['session_id']
                        resume_gateway_url[0] = d['resume_gateway_url']
                        print(f"{get_timestamp()} VC Ready: {token[:10]}...")
                        ws.send(json.dumps({"op": 4, "d": {"guild_id": guild_id, "channel_id": voice_channel_id, "self_mute": True, "self_deaf": False}}))
                        print(f"{get_timestamp()} VC Joined: {token[:10]}...")
                    elif t == 'RESUMED':
                        print(f"{get_timestamp()} VC Resumed: {token[:10]}...")
                
                elif op == 11:
                    heartbeat_acked[0] = True
                elif op == 9:
                    session_id[0] = None
                    resume_gateway_url[0] = None
                    time.sleep(5)
                    break
                elif op == 7:
                    raise WebSocketConnectionClosedException("Reconnect")
        
        except Exception as e:
            print(f"{get_timestamp()} VC Error {token[:10]}: {e}. Retry...")
            if '401' in str(e):
                return
            time.sleep(10)
        finally:
            if ws:
                ws.close()
            stopper.set()
            time.sleep(5)

def main():
    serial = len(sys.argv) > 1 and sys.argv[1] == "--serial"
    if len(sys.argv) > 1 and sys.argv[1] in ["--config", "--setC", "--help"]:
        if sys.argv[1] == "--config" and input("Configure? (y/n): ").lower() == "y":
            configure_info()
        elif sys.argv[1] == "--setC" and input("Set? (y/n): ").lower() == "y":
            set_channel()
        elif sys.argv[1] == "--help":
            show_help()
        return

    info = read_info()
    if not info:
        configure_info()
        return

    channel_url, channel_id, guild_id, voice_channel_id, default_delay, default_sleep = info
    delay = 1  # Hard-set to 1 second
    sleep_time = int(input(f"Sleep [ {default_sleep} ]: ") or default_sleep)

    tokens = load_tokens()
    if not tokens:
        return

    messages = load_messages()
    if not messages:
        return

    print(f"{get_timestamp()} Starting (WARNING: 1s delay may cause bans/rate limits!)")

    vc_executor = ThreadPoolExecutor(max_workers=len(tokens))
    for token in tokens:
        vc_executor.submit(vc_run, token, guild_id, voice_channel_id)
        time.sleep(1)

    msg_executor = ThreadPoolExecutor(max_workers=1 if serial else len(tokens))

    try:
        while True:
            print(f"{get_timestamp()} Cycle start...")
            if serial:
                for token in tokens:
                    messenger_worker(token, channel_id, messages, delay)
            else:
                futures = [msg_executor.submit(messenger_worker, token, channel_id, messages, delay) for token in tokens]
                for future in futures:
                    future.result()

            print(f"{get_timestamp()} Cycle complete!")
            random_sleep(sleep_time, 0, 10)

    except KeyboardInterrupt:
        print(f"{get_timestamp()} Stopping...")
        msg_executor.shutdown(wait=True)
        vc_executor.shutdown(wait=True)
        sys.exit(0)

if __name__ == "__main__":
    main()
