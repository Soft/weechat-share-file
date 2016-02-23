#!/usr/bin/env bash

FILE="$1"

declare -a DEPS
DEPS=( curl )

declare -a NOT_ALLOWED
NOT_ALLOWED=(exe scr rar zip com vbs bat cmd html htm msi)

function check-deps() {
    for prog in "${DEPS[@]}"; do
        hash "$prog" &>/dev/null
        if [[ $? -ne 0 ]]; then
            echo "$prog is required" >&2
            exit 1
        fi
    done
}

function check-ext() {
    local extension="${1##*.}"
    for ext in "${NOT_ALLOWED[@]}"; do
        [[ "$ext" == "$extension" ]] && exit 1
    done
}

function upload() {
    local url="https://uguu.se/api.php?d=upload-tool"
    local name=$(basename "$1")
    local reply=$(curl -F "file=@${1}" \
                       -F "name=${name}" \
                       "$url" \
                       2>/dev/null)
    echo "$reply"
}

check-deps
check-ext "$FILE"
upload "$FILE"
