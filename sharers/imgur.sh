#!/usr/bin/env bash

FILE="$1"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/imgur.conf"

declare -a DEPS
DEPS=( curl jq )

MAX_SIZE=10000000

function upload() {
    local url="https://api.imgur.com/3/image"
    local reply=$(curl -F "image=@\"${1}\"" \
                       -H "Authorization: Client-ID ${IMGUR_CLIENT_ID}" \
                       "$url" \
                       2>/dev/null)
    echo "$reply" | jq -er .data.link
}

function check-deps() {
    for prog in "${DEPS[@]}"; do
        hash "$prog" &>/dev/null
        if [[ $? -ne 0 ]]; then
            echo "$prog is required" >&2
            exit 1
        fi
    done
}

function check-file() {
    local size=$(stat --printf="%s" "$1")
    if [[ "$size" -gt "$MAX_SIZE" ]]; then
        echo "\"$FILE\" is too large" >&2
        exit 1
    fi
}

if [[ -r "$CONFIG" ]]; then
    source "$CONFIG"
fi

if [[ -z "${IMGUR_CLIENT_ID+x}" ]]; then
    echo "IMGUR_CLIENT_ID must be specified" >&2
    exit 1
fi

if [[ ! -r "$FILE" ]]; then
    echo "\"$FILE\" does not exist" >&2
    exit 1
fi

check-deps
check-file "$FILE"
upload "$FILE"
