# coding=utf-8
#
# WeeChat script for quickly sharing files
# Copyright (C) 2016 Samuel Laurén
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

# TODO:
# - Implement program launching
# - Implement commands for editing sharers
# - Changing sorting method on the fly

from __future__ import print_function

import math
import os
import os.path
import re
from collections import namedtuple

try:
    import weechat as wc
except ImportError:
    print("This script must be run under WeeChat.")
    exit(1)

try:
    import magic
    HAS_MAGIC = True
except:
    wc.prnt("", wc.prefix("error") +
            "Package python-magic is required for this script to work.")
    HAS_MAGIC = False

SCRIPT_NAME = "share-file"
SCRIPT_AUTHOR = "Samuel Laurén <samuel.lauren@iki.fi>"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESCRIPTION = "Quickly share files from WeeChat"

SHARE_COMMAND = "share"

SHARE_HELP = """
Quickly share files from WeeChat

When the %(command)s is invoked, it displays a file chooser and lets the user
select a file for sharing. Once the file is selected, the command shares it
using an external application and returns its URL.

The choice of sharing application depends on the type of file in question. This
can be configured via plugins.var.python.%(script)s.sharers.

You might want to consider binding %(command)s to a key.
For example, use
  /key bind meta-o /%(command)s
to bind it to M-o
""".lstrip() % {"command": SHARE_COMMAND,
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


# Matchers take file names
def match_start(query, file):
    return case_transform(file).startswith(case_transform(query))


def match_contains(query, file):
    return case_transform(query) in case_transform(file)


def match_glob(query, file):
    return glob_match(case_transform(query), case_transform(file))


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
        return self.__color(self.selected_color if selected else
                            self.file_color, name)

    def render_dir(self, dir, selected):
        name = dir if self.full_selected and selected else self.abbreviation(
            self.max_length, dir)
        return self.__color(self.selected_color if selected else
                            self.dir_color, name)

    def render(self, input, page, pages, entries):
        start = self.__color(self.separator_color, "[")
        end = self.__color(self.separator_color, "]")
        return "%s: %s%s%s %s%d/%d%s %s" % (self.prompt, start, self.__color(
            self.input_color, input), end, start, page, pages, end,
                                            " ".join(entries))

    def __color(self, color, str):
        return "%s%s%s" % (wc.color(color), str, wc.color("reset"))


class BufferManager(object):
    def __init__(self):
        self.buffers = {}

    def activate(self, buffer):
        dir = wc.config_get_plugin("dir")
        dir = dir if os.path.isdir(dir) else os.getcwd()
        entries = int(wc.config_get_plugin("entries"))
        wrap = str_to_bool(wc.config_get_plugin("wrap"))
        hidden = str_to_bool(wc.config_get_plugin("hidden"))
        assert entries > 0
        browser = Browser(dir, entries, Renderer(), hidden, wrap, get_sorter(),
                          get_matcher())
        self.buffers[buffer] = BufferState(
            wc.buffer_get_string(buffer, "input"), browser)

    def deactivate(self, buffer):
        del self.buffers[buffer]

    def __contains__(self, buffer):
        return buffer in self.buffers

    def __getitem__(self, buffer):
        return self.buffers[buffer]

    def current(self):
        return self.buffers[wc.current_buffer()]


BUFFERS = BufferManager()

Sharer = namedtuple("Sharer", ("mime", "program"))

BufferState = namedtuple("BufferState", ("previous_input", "browser"))


def parse_sharers(string):
    results = []
    for entry in string.split(","):
        parts = entry.split(" ")
        if len(parts) != 2:
            return None
        results.append(Sharer(parts[0], parts[1]))
    return results


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


def find_matching_sharers(sharers, path):
    mime = magic.from_file(path, mime=True)
    return next((l for l in sharers if glob_match(l.mime, mime)), None)


def share(sharers, file):
    matching = find_matching_sharers(sharers, file.path)
    if matching:
        # wc.hook_process(matching.program, 0, "process_hook")
        wc.prnt("",
                "Sharing \"%s\" with %s" % (file.display, matching.program))
    else:
        wc.prnt("", wc.prefix("error") +
                "Failed to share \"%s\": no matching sharer" % file.display)


def force_redraw():
    wc.hook_signal_send("input_text_changed", wc.WEECHAT_HOOK_SIGNAL_STRING,
                        "")


def share_command(data, buffer, args):
    BUFFERS.activate(buffer)
    force_redraw()
    return wc.WEECHAT_RC_OK


def process_hook(data, command, code, out, err):
    if code == wc.WEECHAT_HOOK_PROCESS_ERROR:
        return wc.WEECHAT_RC_OK
    elif code == 0:
        pass  # Return URL
    elif code > 0:
        pass  # Cancel file entry


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
    wc.prnt("", "mod: %s mod-data: %s string: '%s'" %
            (modifier, modifier_data, string))
    buffer = wc.current_buffer()
    if buffer in BUFFERS:
        browser = BUFFERS.current().browser
        string = wc.string_remove_color(string, "")
        if string != browser.input:
            wc.prnt("", "Old and new input differ, setting new")
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
    init_config()
    install_hooks()


if __name__ == "__main__" and HAS_MAGIC:
    main()
