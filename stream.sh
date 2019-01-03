#!/bin/bash

# Get the coordinates of the active window's
# top-left corner, and the window's size.
# This excludes the window decoration.
# https://unix.stackexchange.com/a/14170/105940

>&2 echo "Select the emulator window"

unset x y w h
eval $(xwininfo |
sed -n -e "s/^ \+Absolute upper-left X: \+\([0-9]\+\).*/x=\1/p" \
       -e "s/^ \+Absolute upper-left Y: \+\([0-9]\+\).*/y=\1/p" \
       -e "s/^ \+Width: \+\([0-9]\+\).*/w=\1/p" \
       -e "s/^ \+Height: \+\([0-9]\+\).*/h=\1/p" )


# Use ffmpeg to stream the screen in MJPEG format (since it's easy to parse)
# Outputs to stdout (for use with Python's subprocess.Popen)
ffmpeg -loglevel quiet \
       -f x11grab \
       -video_size "$w"x"$h" \
       -framerate 15 \
       -i :0.0+"$x","$y" \
       -qp 0 \
       -codec:v mjpeg \
       -q:v 1 \
       -an \
       -f mjpeg \
       -preset ultrafast -
