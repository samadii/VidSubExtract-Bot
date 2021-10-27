import requests
import numpy as np
import os, datetime
import pytesseract
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageEmpty
from PIL import Image

#pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# config vars
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
LANG = os.environ.get("SUBTITLE_LANG") #Get this from https://en.m.wikipedia.org/wiki/List_of_ISO_639-2_codes
USE_CROP = os.environ.get("USE_CROP") #[Optional] Set to ANYTHING to enable crop mode

Bot = Client(
    "Bot",
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

#language data for ocr
tessdata = f"https://github.com/tesseract-ocr/tessdata/raw/main/{LANG}.traineddata"
dirs = r"/app/vendor/tessdata"
path = os.path.join(dirs, LANG+".traineddata")
if not os.path.exists(path):
    data = requests.get(tessdata, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    if data.status_code == 200:
        open(path, "wb").write(data.content)
    else:
        print("Either the lang code is wrong or the lang is not supported.")


@Bot.on_message(filters.private & filters.video)
async def main(bot, m):
    msg = await m.reply("`Downloading and Extracting...`", parse_mode='md')
    await m.download("temp/vid.mp4")
    sub_count = 0
    repeated_count = 0
    last_text = " "
    duplicate = True
    lastsub_time = 0
    intervals = [round(num, 2) for num in np.linspace(0,m.video.duration,(m.video.duration-0)*int(1/0.1)+1).tolist()]
    # Extract frames every 100 milliseconds for ocr
    for interval in intervals:
        try:
            os.system(f"ffmpeg -ss {interval} -i temp/vid.mp4 -pix_fmt yuvj422p -vframes 1 -q:v 2 -y temp/output.jpg")

            #Maybe make better recognition
            """
            import cv2  #Install opencv-python-headless
            im = cv2.imread("temp/output.jpg")
            im = cv2.cvtColor(im, cv2.COLOR_BGR2LUV)
            cv2.imwrite("temp/output.jpg", im)
            import PIL.ImageOps
            im = PIL.ImageOps.invert(im)
            im.save("temp/output.jpg")
            """

            if USE_CROP:
                im = Image.open("temp/output.jpg")
                width, height = im.size
                x1 = str(width/7)
                y1 = str(3*(height/4))
                x2 = str(6*(width/7))
                y2 = height
                crop_area = (int(x1.split('.')[0]), int(y1.split('.')[0]), int(x2.split('.')[0]), y2)
                im = im.crop(crop_area)  # Learn how to change crop parameters: https://stackoverflow.com/a/39424357
                #im.show()
                im.save("temp/output.jpg")
            text = pytesseract.image_to_string("temp/output.jpg", LANG)
        except MessageEmpty:
            text = None
            pass
        except Exception as e:
            return print(e)

        if text != None and text[:1].isspace() == False :
            # Check either text is duplicate or not
            commons = list(set(text.rsplit()) & set(last_text.rsplit()))
            if len(text.rsplit()) <= 3 and len(commons) >= 1:
                duplicate = True
                repeated_count += 1
            elif len(text.rsplit()) > 3 and len(commons) >= 3:
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
                f = open("temp/srt.srt", "a+", encoding="utf-8")
                f.write(str(sub_count) + "\n" + from_time + " --> " + to_time + "\n" + last_text + "\n\n")
                duplicate = True
                repeated_count = 0
            last_text = text

        # Write the last dialogue
        if interval == m.video.duration:
            ftime = str(datetime.datetime.fromtimestamp(lastsub_time)+datetime.timedelta(hours=0)).split(' ')[1][:12]
            ttime = str(datetime.datetime.fromtimestamp(lastsub_time+10)+datetime.timedelta(hours=0)).split(' ')[1][:12]
            f = open("temp/srt.srt", "a+", encoding="utf-8")
            f.write(str(sub_count+1) + "\n" + ftime + " --> " + ttime + "\n" + last_text + "\n\n")

    f.close
    await bot.send_document(chat_id=m.chat.id, document="temp/srt.srt" ,caption=m.video.file_name, file_name=m.video.file_name+".srt")
    await msg.delete()
    os.remove("temp/srt.srt")


Bot.run()
