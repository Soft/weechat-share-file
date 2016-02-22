# coding=utf-8
#
# WeeChat script for quickly sharing files
# Copyright (C) 2016 Samuel Laurén <samuel.lauren@iki.fi>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# TODO: exit chooser with a key binding

from __future__ import print_function

import math
import os
import os.path
import re
from collections import namedtuple
from functools import wraps

try:
    import weechat as wc
except ImportError:
    print("This script must be run under WeeChat.")
    exit(1)


def error(message, buffer=""):
    wc.prnt(buffer, wc.prefix("error") + message)


try:
    import magic
    HAS_MAGIC = True
except:
    error("Package python-magic is required for this script to work.")
    HAS_MAGIC = False

SCRIPT_NAME = "share-file"
SCRIPT_AUTHOR = "Samuel Laurén <samuel.lauren@iki.fi>"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESCRIPTION = "Quickly share files from WeeChat"

SHARERS_COMMAND = "sharers"
SHARERS_HELP = "Edit and inspect sharers"
SHARERS_ARGS = "add <mime> <program> [<index>] | del <index> | list"
SHARERS_DESC = """
   add: add association between MIME type and a program
   del: delete association
  list: list associations

Examples:
Associate program upload-image.sh with files of type image/*
  /%(command)s add image/* upload-image.sh
""".lstrip("\n") % {"command": SHARERS_COMMAND}
SHARERS_COMPLETION = "add|del|list"

SHARE_COMMAND = "share"
SHARE_HELP = """
Quickly share files from WeeChat

When the %(share)s is invoked, it displays a file chooser and lets the user
select a file for sharing. The selected file is shared using an external
application and the resulting URL is returned.

The choice of sharing application depends on the type of file in question.
File's MIME type is matched against a list of configured programs and the first
matching program is selected. These program associations can be edited with
/%(sharers)s command.

You might want to consider binding %(share)s to a key.
For example, use
  /key bind meta-o /%(share)s
to bind it to M-o
""".lstrip() % {"share": SHARE_COMMAND,
                "sharers": SHARERS_COMMAND,
                "script": SCRIPT_NAME, }

HOOK_PRIORITY = 5000
HOOKS = []


def natsort_key(k):
    to_key = lambda s: int(s) if s.isdigit() else s
    return [to_key(group) for group in re.split("([0-9]+)", k)]


# Sorters asume list of Files
def sort_by_name(files):
    return sorted(files, key=lambda f: natsort_key(f.display))


def sort_by_mtime(files):
    compare = lambda a, b: os.path.getmtime(b.path) - os.path.getmtime(a.path)
    return sorted(files, cmp=compare)


def sort_by_size(files):
    compare = lambda a, b: os.path.getsize(a.path) - os.path.getsize(b.path)
    return sorted(files, cmp=compare)


SORTERS = {"name": sort_by_name, "mtime": sort_by_mtime, "size": sort_by_size}
DEFAULT_SORTER = sort_by_name


def get_sorter():
    return SORTERS.get(wc.config_get_plugin("sort"), DEFAULT_SORTER)


def case_transform(str):
    if str_to_bool(wc.config_get_plugin("case_insensitive")):
        return str.lower()
    else:
        return str


def case_aware(fn):
    @wraps(fn)
    def wrap(query, file):
        return fn(case_transform(query), case_transform(file))

    return wrap

# Matchers take file names


@case_aware
def match_start(query, file):
    return file.startswith(query)


@case_aware
def match_contains(query, file):
    return query in file


@case_aware
def match_glob(query, file):
    return glob_match(query, file)


FUZZINESS_MAX_DISTANCE = 3


def levenshtein(a, b):
    pass


# TODO: implement
def match_fuzzy(query, file):
    return True


MATCHERS = {"start": match_start,
            "contains": match_contains,
            "fuzzy": match_fuzzy,
            "glob": match_glob}
DEFAULT_MATCHER = match_start


def get_matcher():
    return MATCHERS.get(wc.config_get_plugin("matcher"), DEFAULT_MATCHER)

# Abbreviation methods take a file name and a max length


def abbreviate_none(max, file):
    return file


def abbreviate_end(max, file):
    if len(file) < max:
        return file
    else:
        end = max - len(ABBREVIATION_INDICATOR)
        return file[:end] + ABBREVIATION_INDICATOR


def abbreviate_middle(max, file):
    if len(file) < max:
        return file
    else:
        gap = len(ABBREVIATION_INDICATOR)
        half = (max - gap) // 2
        return file[:half] + ABBREVIATION_INDICATOR + file[half + gap:]


ABBREVIATIONS = {
    "end": abbreviate_end,
    "middle": abbreviate_middle,
    "none": abbreviate_none
}
DEFAULT_ABBREVIATION = abbreviate_none
ABBREVIATION_INDICATOR = "..."


def get_abbreviation():
    return ABBREVIATIONS.get(
        wc.config_get_plugin("abbreviate"), DEFAULT_ABBREVIATION)


File = namedtuple("File", ("path", "display"))


def files(sort, path):
    files = sort([File(path=os.path.abspath(os.path.join(path, f)),
                       display=f) for f in os.listdir(path)])
    # Parent directory's entry is not sorted
    if not is_root(path):
        files.insert(0,
                     File(path=os.path.abspath(os.path.join(path, os.pardir)),
                          display=os.pardir))
    return files


def is_root(path):
    return os.path.dirname(os.path.abspath(path)) == os.path.abspath(path)


def present_keys(dict):
    return ", ".join(dict.viewkeys())


CONFIG = {
    "color_file": ("green", "color for files"),
    "color_dir": ("*cyan", "color for directories"),
    "color_input": ("default", "color for input"),
    "color_selected": ("red,yellow", "color for the selected entry"),
    "color_separator": ("magenta", "color for separators"),
    "entries": ("16", "how many entries to show at once"),
    "prompt": ("Share", "message to display in the file selection prompt"),
    "sharers": ("* echo", "list of mime-type program mappings"),
    "timeout": ("60", "how many seconds to wait for the sharer to finish"),
    "sort": ("name", "how to sort entries (%s)" % present_keys(SORTERS)),
    "matching":
    ("start", "matching method for entries (%s)" % present_keys(MATCHERS)),
    "case_insensitive": ("yes", "is matching case insensitive"),
    "hidden": ("no", "show hidden files"),
    "abbreviate":
    ("end", "abbreviation method (%s)" % present_keys(ABBREVIATIONS)),
    "max_length": ("32", "maximum entry length"),
    "full_selected": ("yes", "do not abbreviate selected entry"),
    "dir": ("", "initial directory"),
    "wrap": ("yes", "selection wraps around")
}


def str_to_bool(s):
    return s.lower() in ("yes", "on", "true")


def color(color, str):
    return "%s%s%s" % (wc.color(color), str, wc.color("reset"))

# TODO: save input bar size and set it to growing for the period browser is open


class Browser(object):
    def __init__(self,
                 dir,
                 entries,
                 renderer,
                 hidden=True,
                 wrap=True,
                 sorter=DEFAULT_SORTER,
                 matcher=DEFAULT_MATCHER):
        self.entries = entries
        self.renderer = renderer
        self.wrap = wrap
        self.hidden = hidden
        self.sorter = sorter
        self.matcher = matcher
        self.change_directory(dir)

    def render(self):
        entries = (self.__format_entry(f, n == self.index)
                   for n, f in enumerate(self.visible_files, self.__offset))
        return self.renderer.render(self.input, self.page + 1, self.pages + 1,
                                    entries)

    def __format_entry(self, file, selected):
        if os.path.isdir(file.path):
            return self.renderer.render_dir(file.display, selected)
        else:
            return self.renderer.render_file(file.display, selected)

    def __is_visible(self, file):
        return self.hidden or \
            file.display == os.pardir or \
            not file.display.startswith(".")

    def __is_matching(self, file):
        if not self.input:
            return True
        return self.matcher(self.input, file.display)

    @property
    def __offset(self):
        return self.page * self.entries

    @property
    def pages(self):
        return int(math.ceil(len(self.filtered_files) / self.entries))

    @property
    def page(self):
        return self.index // self.entries

    @property
    def filtered_files(self):
        return [f
                for f in self.files
                if self.__is_visible(f) and self.__is_matching(f)]

    @property
    def visible_files(self):
        filtered = self.filtered_files
        return filtered[self.__offset:self.__offset + self.entries] \
            if filtered else filtered

    def input_get(self):
        return self.__input

    def input_set(self, val):
        self.__input = val
        self.index = 0

    input = property(input_get, input_set)

    @property
    def selected(self):
        filtered = self.filtered_files
        if filtered:
            return filtered[self.index]

    def change_directory(self, path):
        self.dir = path
        self.files = files(self.sorter, path)
        self.input = ""

    def enter(self):
        if self.filtered_files:
            if os.path.isdir(self.selected.path):
                self.change_directory(self.selected.path)
            else:
                return self.selected

    def next(self):
        filtered = self.filtered_files
        if filtered:
            if len(filtered) > self.index + 1:
                self.index += 1
            elif self.wrap:
                self.index = 0

    def previous(self):
        filtered = self.filtered_files
        if filtered:
            if self.index > 0:
                self.index -= 1
            elif self.wrap:
                self.index = len(filtered) - 1


class Renderer(object):
    def __init__(self):
        self.dir_color = wc.config_get_plugin("color_dir")
        self.file_color = wc.config_get_plugin("color_files")
        self.input_color = wc.config_get_plugin("color_input")
        self.selected_color = wc.config_get_plugin("color_selected")
        self.separator_color = wc.config_get_plugin("color_separator")
        self.prompt = wc.config_get_plugin("prompt")
        self.abbreviation = get_abbreviation()
        self.max_length = int(wc.config_get_plugin("max_length"))
        self.full_selected = str_to_bool(wc.config_get_plugin("full_selected"))

    def render_file(self, file, selected):
        name = file if self.full_selected and selected else self.abbreviation(
            self.max_length, file)
        return color(self.selected_color if selected else self.file_color,
                     name)

    def render_dir(self, dir, selected):
        name = dir if self.full_selected and selected else self.abbreviation(
            self.max_length, dir)
        return color(self.selected_color if selected else self.dir_color, name)

    def render(self, input, page, pages, entries):
        start = color(self.separator_color, "[")
        end = color(self.separator_color, "]")
        return "%s: %s%s%s %s%d/%d%s %s" % (self.prompt, start, color(
            self.input_color, input), end, start, page, pages, end,
                                            " ".join(entries))


class BufferManager(object):
    def __init__(self):
        self.buffers = {}

    def activate(self, buffer):
        dir = wc.config_get_plugin("dir")
        dir = dir if os.path.isdir(dir) else os.getcwd()
        entries = int(wc.config_get_plugin("entries"))
        wrap = str_to_bool(wc.config_get_plugin("wrap"))
        hidden = str_to_bool(wc.config_get_plugin("hidden"))
        input = wc.buffer_get_string(buffer, "input")
        assert entries > 0
        wc.buffer_set(buffer, "input", "")
        browser = Browser(dir, entries, Renderer(), hidden, wrap, get_sorter(),
                          get_matcher())
        self.buffers[buffer] = BufferState(input, browser)

    def deactivate(self, buffer):
        state = self.buffers[buffer]
        del self.buffers[buffer]
        wc.buffer_set(buffer, "input", state.previous_input)

    def __contains__(self, buffer):
        return buffer in self.buffers

    def __getitem__(self, buffer):
        return self.buffers[buffer]

    def current(self):
        return self.buffers[wc.current_buffer()]


BUFFERS = BufferManager()

Sharer = namedtuple("Sharer", ("mime", "program"))

BufferState = namedtuple("BufferState", ("previous_input", "browser"))


def glob_match(glob, string):
    start, end = False, False
    if glob == "*":
        return True
    if glob.startswith("*"):
        glob = glob[1:]
        start = True
    if glob.endswith("*"):
        glob = glob[:-1]
        end = True
    if start and end:
        return glob in string
    elif start:
        return string.endswith(glob)
    elif end:
        return string.startswith(glob)
    else:
        return glob == string


def parse_sharers(string):
    results = []
    if not string:
        return results
    for entry in string.split(","):
        parts = re.split("\s+", entry)
        if len(parts) != 2:
            return None
        results.append(Sharer(parts[0], parts[1]))
    return results


def serialize_sharers(sharers):
    return ",".join("%s %s" % (s.mime, s.program) for s in sharers)


def get_sharers():
    return parse_sharers(wc.config_get_plugin("sharers"))


def set_sharers(sharers):
    wc.config_set_plugin("sharers", serialize_sharers(sharers))


def add_sharer(index, sharer):
    sharers = get_sharers()
    sharers.insert(index, sharer)
    set_sharers(sharers)


def delete_sharer(index):
    sharers = get_sharers()
    del sharers[index]
    set_sharers(sharers)


def find_matching_sharer(sharers, path):
    mime = magic.from_file(path, mime=True)
    return next((l for l in sharers if glob_match(l.mime, mime)), None)


DISPLAY_MIME_COLOR = "yellow"
DISPLAY_PROGRAM_COLOR = "cyan"


def sharers_list_command(args):
    sharers = get_sharers()
    max_length = max(map(lambda s: len(s.mime), sharers) or [0])
    wc.prnt("", "All sharers:")
    for n, sharer in enumerate(sharers, 1):
        wc.prnt("", "  %d. %s%s %s" %
                (n, color(DISPLAY_MIME_COLOR, sharer.mime),
                 " " * (max_length - len(sharer.mime)),
                 color(DISPLAY_PROGRAM_COLOR, sharer.program)))
    return wc.WEECHAT_RC_OK


def sharers_add_command(args):
    if not 2 <= len(args) <= 3:
        return wc.WEECHAT_RC_ERROR
    sharers = get_sharers()
    if len(args) == 3:
        if not args[2].isdigit() or not 1 <= int(args[2]) <= len(sharers) + 1:
            return wc.WEECHAT_RC_ERROR
        index = int(args[2]) - 1
    else:
        index = len(sharers)
    add_sharer(index, Sharer(mime=args[0], program=args[1]))
    return wc.WEECHAT_RC_OK


def sharers_del_command(args):
    if len(args) != 1 or not args[0].isdigit():
        return wc.WEECHAT_RC_ERROR
    sharers = get_sharers()
    index = int(args[0])
    if not 1 <= index <= len(sharers):
        return wc.WEECHAT_RC_ERROR
    delete_sharer(index - 1)
    return wc.WEECHAT_RC_OK


SHARERS_SUB_COMMANDS = {
    "add": sharers_add_command,
    "del": sharers_del_command,
    "list": sharers_list_command
}


def sharers_command(data, buffer, args):
    args = re.split("\s+", args)
    if not args:
        return wc.WEECHAT_RC_ERROR
    return SHARERS_SUB_COMMANDS.get(args[0],
                                    lambda _: wc.WEECHAT_RC_ERROR)(args[1:])


def force_redraw():
    wc.hook_signal_send("input_text_changed", \
                        wc.WEECHAT_HOOK_SIGNAL_STRING, "")


def share_command(data, buffer, args):
    BUFFERS.activate(buffer)
    force_redraw()
    return wc.WEECHAT_RC_OK


def process_hook(data, command, code, out, err):
    if code == wc.WEECHAT_HOOK_PROCESS_ERROR:
        error("Sharing failed: failed to start the program", data)
    elif code == wc.WEECHAT_HOOK_PROCESS_RUNNING:
        # TODO: handle multiple calls
        pass
    elif code == 0:
        input_append_value(data, out)
    elif code > 0:
        error("Sharing failed: non-zero status", data)
    return wc.WEECHAT_RC_OK


def input_append_value(buffer, value):
    old = wc.string_remove_color(wc.buffer_get_string(buffer, "input"), "")
    space = " " if old and old[-1] != " " else ""
    new = old + space + value
    wc.buffer_set(buffer, "input", new)
    wc.buffer_set(buffer, "input_pos", str(len(new) - 1))


def share(sharers, file):
    matching = find_matching_sharer(sharers, file.path)
    timeout = int(wc.config_get_plugin("timeout")) * 1000
    if matching:
        args = {"arg1": file.path}
        wc.hook_process_hashtable(matching.program, args, timeout,
                                  "process_hook", wc.current_buffer())
    else:
        error("Failed to share \"%s\": no matching sharer" % file.display)


def input_hook(data, buffer, command):
    if buffer not in BUFFERS:
        return wc.WEECHAT_RC_OK

    browser = BUFFERS.current().browser
    if command == "/input return":
        file = browser.enter()
        if file:
            sharers = parse_sharers(wc.config_get_plugin("sharers"))
            share(sharers, file)
            BUFFERS.deactivate(buffer)
        else:
            wc.buffer_set(buffer, "input", "")
    elif command == "/input complete_next":
        browser.next()
    elif command == "/input complete_previous":
        browser.previous()
    else:
        return wc.WEECHAT_RC_OK
    force_redraw()
    return wc.WEECHAT_RC_OK_EAT


def modifier_hook(data, modifier, modifier_data, string):
    buffer = wc.current_buffer()
    if buffer in BUFFERS:
        browser = BUFFERS.current().browser
        string = wc.string_remove_color(string, "")
        if string != browser.input:
            browser.input = string
        return browser.render()
    return string


def init_config():
    for option, (default, help) in CONFIG.viewitems():
        if not wc.config_is_set_plugin(option):
            wc.config_set_plugin(option, default)
        wc.config_set_desc_plugin(option,
                                  "%s (default: \"%s\")" % (help, default))


def unload():
    for hook in HOOKS:
        wc.unhook(hook)
    return wc.WEECHAT_RC_OK


def install_hooks():
    HOOKS.extend([
        wc.hook_command_run("%d|%s" % (HOOK_PRIORITY, "/input *"),
                            "input_hook", ""),
        wc.hook_modifier("%d|%s" % (HOOK_PRIORITY, "input_text_display_with_cursor"),
                              "modifier_hook", "")
    ]) # yapf: disable

def main():
    if not wc.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION,
                       SCRIPT_LICENSE, SCRIPT_DESCRIPTION, "unload", ""):
        return
    wc.hook_command(SHARE_COMMAND, SHARE_HELP, "", "", "", "share_command", "")
    wc.hook_command(SHARERS_COMMAND, SHARERS_HELP, SHARERS_ARGS, SHARERS_DESC,
                    SHARERS_COMPLETION, "sharers_command", "")
    init_config()
    install_hooks()


if __name__ == "__main__" and HAS_MAGIC:
    main()
