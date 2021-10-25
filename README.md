# Video Subtitle Extractor Bot

A simple Telegram bot to extract hard-coded subtitle from videos using FFmpeg & Tesseract.


Note that the accuracy of recognition depends on the subtitle font and its visibility.

## Deploy to Heroku

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/samadii/VidSubExtract-Bot)


## Local Deploying

1. Clone the repo
   ```
   git clone https://github.com/samadii/VidSubExtract-Bot
   ```

2. Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and [FFmpeg](www.ffmpeg.org). 
   
3. Go to [this line](https://github.com/samadii/VidSubExtract-Bot/blob/master/main.py#L9) and fill the inverted commas with the PATH where Tesseract is installed.

4. Also fill [this path](https://github.com/samadii/VidSubExtract-Bot/blob/master/main.py#L53) with the path of the tessdata folder.
   
5. Enter the directory
   ```
   cd VidSubExtract-Bot
   ```
  
6. Install all requirements using pip.
   ```
   pip3 install -r requirements.txt
   ```

7. Run the file
   ```
   python3 main.py
   ```

## Environment Variables

- `API_ID` - Get this from [my.telegram.org](https://my.telegram.org/auth)
- `API_HASH` - Get this from [my.telegram.org](https://my.telegram.org/auth)
- `BOT_TOKEN` - Get this from [@BotFather](https://t.me/BotFather)
- `SUBTITLE_LANG` - Get this from [list of ISO 639-2 language codes](https://en.m.wikipedia.org/wiki/List_of_ISO_639-2_codes)

### Devs: 
- [@samadii](https://github.com/samadii)
