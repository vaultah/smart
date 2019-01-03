import argparse
import asyncio
import functools
import io
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread

import janus
import numpy as np
import tesserocr
import websockets

from skimage.color import rgb2gray
from skimage import filters
from skimage import util
from scipy import ndimage as ndi
from PIL import Image


WEBSOCKET_HOST = 'localhost'
WEBSOCKET_PORT = 8779
TESSDATA = '/usr/share/tesseract-ocr/tessdata'


def _normalize_whitespace(string):
    return re.sub(r'(\s)\1{1,}', r'\1', string).strip()


def invert_button_colors(img):
    """ Find the buttons, invert their colors """
    # Thanks, Andras
    options = util.invert(img)
    label, num_features = ndi.label(options)

    for feat in range(1, num_features + 1):
        inds = np.where(label == feat)
        if (0 in inds[0] or options.shape[0]-1 in inds[0]
            or 0 in inds[1] or options.shape[1]-1 in inds[1]):
            options[inds] = 0

    return options


def optimize(img):
    """ Convert to grayscale and apply the threshold """
    img = rgb2gray(img)
    return img >= filters.threshold_minimum(img)


def ocr(question, answers):
    """ Perform the OCR """
    start = time.perf_counter()
    question = Image.fromarray((question * 255).astype(np.uint8))
    answers = Image.fromarray((answers * 255).astype(np.uint8))

    with ThreadPoolExecutor() as executor:
        a = executor.submit(tesserocr.image_to_text, question,
                        lang='rus+eng', path=TESSDATA, psm=6)
        b = executor.submit(tesserocr.image_to_text, answers,
                        lang='rus+eng', path=TESSDATA, psm=4)
        question, answers = a.result(), b.result()

    question = _normalize_whitespace(question.lower())
    # The first line is noise
    try:
        _, question = question.split('\n', 1)
    except ValueError:
        pass
    question = re.sub(r'\bне\b', '', question, flags=re.I)
    question = question.translate(str.maketrans('«»\n', '"" '))

    answers = _normalize_whitespace(answers.lower())
    answers = answers.split('\n')

    print('OCR completed in', time.perf_counter() - start)
    print(f'Clean question: {question!r}')
    print('Answers:', answers)
    return question, answers


def frame_processor(queue, done):
    prev_loaded = None

    while True:
        frame = queue.get()
        frame = np.asarray(frame)
        height, width, _ = frame.shape

        # Once the bottom part of the third button is white, we know
        # the answers (and the question) have finished loading
        if np.any(frame[int(0.54 * height), width // 4:width // 4 * 3] != 255):
            continue

        # Excludes the viewer count and the countdown timer
        question = optimize(frame[int(0.11 * height):int(0.32 * height)])

        # Check similarity
        # Each question should be processed once
        if prev_loaded is None or np.sum(prev_loaded == question) / question.size <= 0.99:
            prev_loaded = question

            # Empty the queue
            for _ in range(queue.qsize()):
                try:
                    queue.get_nowait()
                except janus.SyncQueueEmpty:
                    break

            buttons = optimize(frame[int(0.32 * height):int(0.56 * height)])
            answers = invert_button_colors(buttons)
            result = ocr(question, answers)
            done(result)


async def ws_handler(queues, websocket, path):
    """ Handle WebSocket connections """
    result_queue = janus.Queue()
    queues.append(result_queue)

    try:
        while True:
            question, answers = await result_queue.async_q.get()
            # Generate search queries
            queries = [question]
            queries += [f'{question} {a}' for a in answers]
            asyncio.ensure_future(websocket.send(json.dumps(queries)))
    finally:
        queues.remove(result_queue)


def notify_all(queues, result):
    """ Send the result to all connected clients """
    for x in queues:
        x.sync_q.put_nowait(result)


def create_stream(queue):
    """ Start the stream, extract JPEG frames, send them to the queue """
    script = Path(__file__).with_name('stream.sh')
    stream = subprocess.Popen(['sh', str(script)], stdout=subprocess.PIPE)
    content = b''
    frame_count = 0
    last_frame = time.perf_counter()

    while True:
        chunk = stream.stdout.read(8_192)
        content += chunk
        soi = content.find(b'\xFF\xD8')
        eoi = content.find(b'\xFF\xD9')

        if soi != -1 and eoi != -1:
            frame_count += 1
            end = time.perf_counter()
            print(f'[#{frame_count:>5}]', 'Since last frame:', end - last_frame)
            last_frame = end

            img = Image.open(io.BytesIO(content[soi:eoi+2]))
            queue.put(img)
            content = content[eoi+2:]


async def main():
    frame_queue = janus.Queue(maxsize=100)
    client_queues = []

    # Wait for frames in another thread
    on_done = functools.partial(notify_all, client_queues)
    Thread(target=frame_processor, args=(frame_queue.sync_q, on_done)).start()
    # Actually start the stream
    Thread(target=create_stream, args=(frame_queue.sync_q,)).start()

    # Start the WS server
    ws = functools.partial(ws_handler, client_queues)
    server = await websockets.serve(ws, WEBSOCKET_HOST, WEBSOCKET_PORT)
    # Keep it running
    await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
