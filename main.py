import requests
import subprocess
import numpy as np
import os, datetime, json, time
import pytesseract
from display_progress import progress_for_pyrogram
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image

#pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# config vars
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
LANG = os.environ.get("SUBTITLE_LANG") #Get this from https://en.m.wikipedia.org/wiki/List_of_ISO_639-2_codes
USE_CROP = os.environ.get("USE_CROP") #[Optional] Set to ANYTHING to enable crop mode

Bot = Client(
    "VidSubExtract-Bot",
    bot_token = BOT_TOKEN,
    api_id = API_ID,
    api_hash = API_HASH
)

START_TXT = """
Hi {}
I am Subtitle Extractor Bot.

> `I can extract hard-coded subtitle from videos.`

Send me a video to get started.
"""

START_BTN = InlineKeyboardMarkup(
        [[
        InlineKeyboardButton("Source Code", url="https://github.com/samadii/VidSubExtract-Bot"),
        ]]
    )


@Bot.on_message(filters.command(["start"]))
async def start(bot, update):
    text = START_TXT.format(update.from_user.mention)
    reply_markup = START_BTN
    await update.reply_text(
        text=text,
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

@Bot.on_message(filters.command(["cancel"]))
async def cancel_progress(_, m):
    try:
        os.remove("temp/vid.mp4")
    except:
        await m.reply("can't cancel. maybe there wasn't any progress in process.")
    else:
        await m.reply("canceled successfully.")

#language data for ocr
tessdata = f"https://github.com/tesseract-ocr/tessdata/raw/main/{LANG}.traineddata"
dirs = r"/app/vendor/tessdata"
path = os.path.join(dirs, f"{LANG}.traineddata")
if not os.path.exists(path):
    data = requests.get(tessdata, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    if data.status_code == 200:
        open(path, "wb").write(data.content)
    else:
        print("Either the lang code is wrong or the lang is not supported.")


@Bot.on_message(filters.private & (filters.video | filters.document))
async def main(bot, m):
    if m.document and not m.document.mime_type.startswith("video/"):
        return
    media = m.video or m.document
    msg = await m.reply("`Downloading..`", parse_mode='md')
    c_time = time.time()
    file_dl_path = await bot.download_media(message=m, file_name="temp/vid.mp4", progress=progress_for_pyrogram, progress_args=("Downloading..", msg, c_time))
    await msg.edit("`Now Extracting..`\n\n for cancel progress, send /cancel", parse_mode='md')
    if m.video:
        duration = m.video.duration
    else:
        video_info = subprocess.check_output(f'ffprobe -v quiet -show_streams -select_streams v:0 -of json "{file_dl_path}"', shell=True).decode()
        fields = json.loads(video_info)['streams'][0]
        duration = int(fields['duration'].split(".")[0])
    sub_count = 0
    repeated_count = 0
    last_text = " "
    duplicate = True
    lastsub_time = 0
    intervals = [round(num, 2) for num in np.linspace(0,duration,(duration-0)*int(1/0.1)+1).tolist()]
    # Extract frames every 100 milliseconds for ocr
    for interval in intervals:
        try:
            command = os.system(f'ffmpeg -ss {interval} -i "{file_dl_path}" -pix_fmt yuvj422p -vframes 1 -q:v 2 -y temp/output.jpg')
            if command != 0:
                return

            #Probably makes better recognition
            """
            import cv2  #Install opencv-python
            img = cv2.imread("temp/output.jpg")
            img = cv2.cvtColor(im, cv2.COLOR_BGR2LUV)
            cv2.imwrite("temp/output.jpg", img)
            import PIL.ImageOps
            img = PIL.ImageOps.invert(img)
            img.save("temp/output.jpg")
            """

            if USE_CROP:
                img = Image.open("temp/output.jpg")
                width, height = img.size
                x1 = width // 7
                y1 = 3 * (height // 4)
                x2 = 6 * (width // 7)
                y2 = height
                crop_area = (x1, y1, x2, y2)
                cropped = img.crop(crop_area) # Learn how to change crop parameters: https://stackoverflow.com/a/39424357
                #cropped.show()
                cropped.save("temp/output.jpg")
            text = pytesseract.image_to_string("temp/output.jpg", LANG)
        except Exception as e:
            print(e)
            text = None
            pass

        if text != None and text[:1].isspace() == False :
            # Check either text is duplicate or not
            commons = list(set(text.split()) & set(last_text.split()))
            if (len(text.split()) <= 3 and len(commons) != 0) or (len(text.split()) == 4 and len(commons) > 1):
                duplicate = True
                repeated_count += 1
            elif len(text.split()) > 4 and len(commons) > 2:
                duplicate = True
                repeated_count += 1
            else:
                duplicate = False

            # time of the last dialogue
            if duplicate == False:
                lastsub_time = interval
                
            # Write the dialogues text
            if repeated_count != 0 and duplicate == False:
                sub_count += 1
                from_time = str(datetime.datetime.fromtimestamp(interval-0.1-repeated_count*0.1)+datetime.timedelta(hours=0)).split(' ')[1][:12]
                to_time = str(datetime.datetime.fromtimestamp(interval)+datetime.timedelta(hours=0)).split(' ')[1][:12]
                from_time = f"{from_time}.000" if not "." in from_time else from_time
                to_time = f"{to_time}.000" if not "." in to_time else to_time
                f = open("temp/srt.srt", "a+", encoding="utf-8")
                f.write(str(sub_count) + "\n" + from_time + " --> " + to_time + "\n" + last_text + "\n\n")
                duplicate = True
                repeated_count = 0
            last_text = text

        # Write the last dialogue
        if interval == duration:
            ftime = str(datetime.datetime.fromtimestamp(lastsub_time)+datetime.timedelta(hours=0)).split(' ')[1][:12]
            ttime = str(datetime.datetime.fromtimestamp(lastsub_time+10)+datetime.timedelta(hours=0)).split(' ')[1][:12]
            ftime = f"{ftime}.000" if not "." in ftime else ftime
            ttime = f"{ttime}.000" if not "." in ttime else ttime
            f = open("temp/srt.srt", "a+", encoding="utf-8")
            f.write(str(sub_count+1) + "\n" + ftime + " --> " + ttime + "\n" + last_text + "\n\n")

    f.close
    await bot.send_document(chat_id=m.chat.id, document="temp/srt.srt" , file_name=media.file_name.rsplit('.', 1)[0]+".srt")
    await msg.delete()
    os.remove(file_dl_path)
    os.remove("temp/srt.srt")


Bot.run()
