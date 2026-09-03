import os
import json
import asyncio
import time
import random
import urllib.parse
import re
import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestWebViewRequest
from pathlib import Path
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

API_ID = int(os.getenv("TG_API_ID") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
BOT_USERNAME = "MoolasBot"

APP_START_URL = "https://moola-peach.vercel.app/"
BASE_API = "https://moola-bot-runner.mrankit4892.workers.dev/api"

# لیست کامل و بدون نقص تسک‌های سوشال تاییدشده از لاگ‌ها
KNOWN_SOCIAL_TASKS = [
    # تلگرام (Telegram)
    "join_channel",
    "channel_join",
    "join_dollarbumper",
    "join_partner",
    "boost_channel",

    # یوتیوب (YouTube)
    "subscribe_youtube",
    "yt_like",
    "yt_share",
    "yt_comment",
    "yt2_comment",

    # توییتر / ایکس (X - Twitter)
    "follow_x",
    "retweet",
    "x_like",
    "x_retweet2",
    "x_comment",
    "x_vote",
    "x_engage_all",
    "react_post",

    # تیک‌تاک (TikTok)
    "tt_comment1",
    "tt_like2",
    "tt_follow",
    "tt_share",

    # فیس‌بوک (Facebook)
    "fb_follow",
    "fb_engage"
]

RAW_ACCOUNTS = os.getenv("ACCOUNTS_JSON")
if RAW_ACCOUNTS:
    try:
        ACCOUNTS = json.loads(RAW_ACCOUNTS)
    except Exception as e:
        print(f"Error parsing ACCOUNTS_JSON: {e}")
        ACCOUNTS = []
elif os.path.exists("accounts.json"):
    try:
        with open("accounts.json", "r", encoding="utf-8") as f:
            ACCOUNTS = json.load(f)
    except Exception as e:
        print(f"Error reading accounts.json: {e}")
        ACCOUNTS = []
else:
    ACCOUNTS = []

def get_account_headers(acc, init_data):
    ua = acc.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    return {
        "User-Agent": ua,
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://moola-peach.vercel.app",
        "Referer": "https://moola-peach.vercel.app/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "x-init-data": init_data
    }

async def fetch_init_data(session_str):
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    bot_peer = await client.get_input_entity(BOT_USERNAME)

    web_view = await client(RequestWebViewRequest(
        peer=bot_peer,
        bot=bot_peer,
        platform="android",
        from_bot_menu=False,
        url=APP_START_URL
    ))
    await client.disconnect()

    match = re.search(r"#tgWebAppData=([^&]+)", web_view.url)
    if match:
        return urllib.parse.unquote(match.group(1))

    parsed_url = urllib.parse.urlparse(web_view.url)
    params = urllib.parse.parse_qs(parsed_url.fragment)
    return params.get("tgWebAppData", [""])[0]

async def process_account(acc):
    jitter = random.uniform(3.0, 15.0)
    await asyncio.sleep(jitter)

    acc_name = acc.get("name", "Account")
    print(f"\n[{acc_name}] Fetching webview initData...")
    
    try:
        init_data = await fetch_init_data(acc["session"])
    except Exception as e:
        print(f"[{acc_name}] Failed to get initData: {e}")
        return

    headers = get_account_headers(acc, init_data)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        current_user = None

        # ۱. دریافت اولیه وضعیت کاربر همراه با Retry
        for attempt in range(1, 4):
            try:
                async with session.post(f"{BASE_API}/mine/start", json={}) as s_resp:
                    if s_resp.status == 200:
                        s_data = await s_resp.json()
                        current_user = s_data.get("user", {})
                        break
                    else:
                        print(f"[{acc_name}] Initial fetch HTTP {s_resp.status}, retrying ({attempt}/3)...")
            except Exception as e:
                print(f"[{acc_name}] Initial fetch network glitch ({e}). Retrying ({attempt}/3)...")
            await asyncio.sleep(2.5)

        if not current_user:
            print(f"[{acc_name}] Could not retrieve user state after retries. Skipping account.")
            return

        # بررسی وضعیت ماینینگ و استارت در صورت لزوم
        mining = current_user.get("mining", {})
        is_active = mining.get("active", False)
        ends_at = mining.get("endsAt") or 0
        now_ms = int(time.time() * 1000)

        if not is_active or now_ms >= ends_at:
            print(f"[{acc_name}] Mining is not active/finished. Claiming & Starting...")
            # الف) تلاش برای کلیم ماین قبلی
            try:
                async with session.post(f"{BASE_API}/mine/claim", json={}) as c_resp:
                    if c_resp.status == 200:
                        c_data = await c_resp.json()
                        current_user = c_data.get("user", current_user)
                        print(f"[{acc_name}] [+] Mining Claimed: +{c_data.get('claimed', 0)} MOOLA")
            except Exception:
                pass

            # ب) ارسال درخواست استارت ماین
            try:
                async with session.post(f"{BASE_API}/mine/start", json={}) as start_resp:
                    if start_resp.status == 200:
                        start_data = await start_resp.json()
                        current_user = start_data.get("user", current_user)
                        mining = current_user.get("mining", {})
                        print(f"[{acc_name}] [+] Mining Started successfully: EndsAt={mining.get('endsAt')}")
                    else:
                        print(f"[{acc_name}] [-] Start button failed: {start_resp.status}")
            except Exception as e:
                print(f"[{acc_name}] Error starting mine: {e}")
        else:
            remaining_mins = max(0, int((ends_at - now_ms) / 60000))
            print(f"[{acc_name}] Mining is already running ({remaining_mins} mins remaining).")

        # ۲. چک‌این روزانه (Daily Check-in)
        checkin = current_user.get("checkin", {})
        if checkin.get("canClaim"):
            print(f"[{acc_name}] Claiming Daily Check-in...")
            try:
                async with session.post(f"{BASE_API}/tasks/checkin", json={}) as ch_resp:
                    if ch_resp.status == 200:
                        ch_data = await ch_resp.json()
                        current_user = ch_data.get("user", current_user)
                        print(f"[{acc_name}] [+] Check-in claimed! Day: {ch_data.get('day')}, Reward: {ch_data.get('reward')}")
                    else:
                        print(f"[{acc_name}] [-] Check-in failed: {ch_resp.status}")
            except Exception as e:
                print(f"[{acc_name}] Check-in error: {e}")

        # ۳. انجام تسک‌های سوشال مدیا (همراه با مکانیزم ضدقطعی Retry)
        social_done = set(current_user.get("socialDone", []))
        for task_id in KNOWN_SOCIAL_TASKS:
            if task_id not in social_done:
                print(f"[{acc_name}] Submitting task: {task_id}...")
                retries = 0
                while retries < 3:
                    try:
                        async with session.post(f"{BASE_API}/tasks/social", json={"taskId": task_id}) as t_resp:
                            if t_resp.status == 200:
                                t_data = await t_resp.json()
                                if t_data.get("credited"):
                                    current_user = t_data.get("user", current_user)
                                    print(f"[{acc_name}] [+] Task {task_id} credited! Reward: +{t_data.get('reward')}")
                                else:
                                    print(f"[{acc_name}] [-] Task {task_id} response: credited=false")
                                break
                            else:
                                print(f"[{acc_name}] [-] Task {task_id} HTTP error: {t_resp.status}")
                                break
                    except Exception as e:
                        retries += 1
                        print(f"[{acc_name}] Task {task_id} network glitch ({e}). Retrying ({retries}/3)...")
                        await asyncio.sleep(2.5)
                await asyncio.sleep(random.uniform(2.0, 3.5))

        # ۴. پردازش تبلیغات
        ads_info = current_user.get("ads", {})

        # الف) تبلیغات استاندارد (Watch - ۱۰ بار)
        watched = ads_info.get("watched", 0)
        watch_total = ads_info.get("watchTotal", 10)
        retries = 0
        while watched < watch_total:
            print(f"[{acc_name}] Watching standard ad ({watched + 1}/{watch_total})...")
            try:
                async with session.post(f"{BASE_API}/tasks/ad", json={"type": "watch"}) as ad_resp:
                    if ad_resp.status == 200:
                        ad_data = await ad_resp.json()
                        if ad_data.get("reward") is not None or ad_data.get("credited") is True:
                            current_user = ad_data.get("user", current_user)
                            watched = current_user.get("ads", {}).get("watched", watched + 1)
                            print(f"[{acc_name}] [+] Standard ad finished! Reward: +{ad_data.get('reward')}")
                            retries = 0
                        else:
                            print(f"[{acc_name}] [-] No standard ad available right now.")
                            break
                    else:
                        print(f"[{acc_name}] [-] Standard ad failed: HTTP {ad_resp.status}")
                        break
            except Exception as e:
                retries += 1
                print(f"[{acc_name}] Network glitch ({e}). Retrying ({retries}/3)...")
                if retries >= 3:
                    break
                await asyncio.sleep(3.0)
                continue
            await asyncio.sleep(random.uniform(5.5, 8.0))

        # ب) تبلیغات تاییدیه (Verify - ۵ بار با تاخیر ۵.۵ ثانیه)
        verified = ads_info.get("verified", 0)
        verify_total = ads_info.get("verifyTotal", 5)
        retries = 0
        while verified < verify_total:
            print(f"[{acc_name}] Processing verify ad ({verified + 1}/{verify_total})...")
            await asyncio.sleep(5.5)
            try:
                async with session.post(f"{BASE_API}/tasks/ad", json={"type": "verify"}) as v_resp:
                    if v_resp.status == 200:
                        v_data = await v_resp.json()
                        if v_data.get("reward") is not None or v_data.get("credited") is True:
                            current_user = v_data.get("user", current_user)
                            verified = current_user.get("ads", {}).get("verified", verified + 1)
                            print(f"[{acc_name}] [+] Verify ad finished! Reward: +{v_data.get('reward')}")
                            retries = 0
                        else:
                            print(f"[{acc_name}] [-] No verify ad available right now.")
                            break
                    else:
                        print(f"[{acc_name}] [-] Verify ad failed: HTTP {v_resp.status}")
                        break
            except Exception as e:
                retries += 1
                print(f"[{acc_name}] Network glitch ({e}). Retrying ({retries}/3)...")
                if retries >= 3:
                    break
                await asyncio.sleep(3.0)
                continue
            await asyncio.sleep(random.uniform(2.0, 3.5))

        # ج) تبلیغات بونوس (Bonus / Watch2 - ۱۰ بار)
        watched2 = ads_info.get("watched2", 0)
        watch2_total = ads_info.get("watch2Total", 10)
        retries = 0
        while watched2 < watch2_total:
            print(f"[{acc_name}] Watching bonus ad ({watched2 + 1}/{watch2_total})...")
            try:
                async with session.post(f"{BASE_API}/tasks/ad", json={"type": "watch2"}) as b_resp:
                    if b_resp.status == 200:
                        b_data = await b_resp.json()
                        if b_data.get("reward") is not None or b_data.get("credited") is True:
                            current_user = b_data.get("user", current_user)
                            watched2 = current_user.get("ads", {}).get("watched2", watched2 + 1)
                            print(f"[{acc_name}] [+] Bonus ad finished! Reward: +{b_data.get('reward')}")
                            retries = 0
                        else:
                            print(f"[{acc_name}] [-] No bonus ad available right now.")
                            break
                    else:
                        print(f"[{acc_name}] [-] Bonus ad failed: HTTP {b_resp.status}")
                        break
            except Exception as e:
                retries += 1
                print(f"[{acc_name}] Network glitch ({e}). Retrying ({retries}/3)...")
                if retries >= 3:
                    break
                await asyncio.sleep(3.0)
                continue
            await asyncio.sleep(random.uniform(5.5, 8.0))

        final_bal = current_user.get("balance", "N/A")
        print(f"[{acc_name}] Finished! Final Balance: {final_bal} MOOLA")

async def main():
    if not ACCOUNTS:
        print("No accounts loaded. Ensure ACCOUNTS_JSON or accounts.json is set.")
        return

    print("==================================================")
    print(f">>> Processing {len(ACCOUNTS)} accounts for Moola ($MOOLA)")
    print("==================================================")

    tasks = [process_account(acc) for acc in ACCOUNTS]
    await asyncio.gather(*tasks)

    print("\n==================================================")
    print(">>> All accounts processed successfully.")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())