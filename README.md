## Smart

I made this to cheat in the Russian clone of HQ Trivia called [Clever](https://vk.com/clever)
([Google Play](https://play.google.com/store/apps/details?id=com.vk.quiz)).

It was possible to extract answers from the UI hierarchy (for example, with `uiautomator dump`),
but the question text seemed to be delivered as part of the stream. For that reason, the simplest
solution was to create a stream of my phone's screen using
[this great app](https://play.google.com/store/apps/details?id=info.dvkr.screenstream),
then use my own script to

  - break that stream into individual frames (MJPEG is *very* nice to work with)
  - find the first frame with fully-loaded question text and answer buttons (once for every question)
  - optimize that frame for OCR
  - spawn the Tesseract process to perform OCR on the question and answers areas of the frame
  - launch a browser, open Yandex search results for the question (as returned by Tesseract)
  - use a browser extension to highlight answers (as returned by Tesseract) on that page

The latency was *high*: at least one second (stream latency) + around 1.5 seconds (OCR) +
around one second to open a new browser tab + time to load the search results. On top of that,
low quality setting for the stream resulted in poor OCR results, while high quality setting
(predictably) resulted in even greater latency.

 After a few iterations the project became what it is now:

  - the Clever app runs in Android emulator on the same machine as the script
  - ffmpeg streams the emulator window in MJPEG format to stdout in highest quality
  - my script uses `subprocess` to read the stream, optimizes frames, runs two separate threads
  for Tesseract in parallel, and finally sends the OCR results to the
  [browser extension](https://github.com/vaultah/smart-extension) via a WebSocket connection
  - the extension loads and displays Yandex search results for the question AND three combinations
  of the question and one of the answers in four iframes
