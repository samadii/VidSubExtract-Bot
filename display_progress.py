# (c) Shrimadhav U K

import math
import time

PROGRESS = """
Percentage : {0}%
Done: {1}
Total: {2}
Speed: {3}/s
ETA: {4}
"""


async def progress_for_pyrogram(current, total, ud_type, message, start):
    if not total:
        return

    now = time.time()
    diff = max(now - start, 0.001)
    if current != total and int(diff) % 10 not in (0, 1):
        return

    percentage = min(100, current * 100 / total)
    speed = current / diff
    elapsed_time = round(diff) * 1000
    time_to_completion = round((total - current) / speed) * 1000 if speed > 0 else 0
    estimated_total_time = elapsed_time + time_to_completion

    elapsed_time = TimeFormatter(milliseconds=elapsed_time)
    estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)

    progress = "[{0}{1}] \n".format(
        "".join(["●" for _ in range(math.floor(percentage / 5))]),
        "".join(["○" for _ in range(20 - math.floor(percentage / 5))]),
    )

    tmp = progress + PROGRESS.format(
        round(percentage, 2),
        humanbytes(current),
        humanbytes(total),
        humanbytes(speed),
        estimated_total_time if estimated_total_time else "0 s",
    )
    try:
        await message.edit(
            text="**{}**\n\n {}".format(ud_type, tmp),
            parse_mode="markdown",
        )
    except Exception:
        pass


def humanbytes(size):
    if not size:
        return "0 B"
    power = 1024
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    index = 0
    while size >= power and index < len(units) - 1:
        size /= power
        index += 1
    return f"{size:.2f} {units[index]}"


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")
    if milliseconds:
        parts.append(f"{milliseconds}ms")
    return ", ".join(parts)
