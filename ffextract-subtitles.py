#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=line-too-long, invalid-name, bad-continuation


"""
Extract subtitles form movies, using ffmpeg

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import os
import glob
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from typing import NamedTuple
import subprocess
import json


class FFProbeResult(NamedTuple):
    ''' ffmpeg probe result'''
    return_code: int
    json: str
    error: str

def ffprobe(file_path) -> FFProbeResult:
    ''' return ffprobe in json format '''
    command_array = ["ffprobe",
                     "-v", "quiet",
                     "-print_format", "json",
                     "-show_format",
                     "-show_streams",
                     file_path]
    try:
        result = subprocess.run(command_array, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf8', check=True)
    except (UnicodeDecodeError, subprocess.CalledProcessError) as _e:
        return FFProbeResult(return_code=1212, json='', error=str(_e))
    return FFProbeResult(return_code=result.returncode,
                         json=result.stdout,
                         error=result.stderr)


def ffsubextract(file_path, subtitle_index, fileout_path):
    ''' extract subtitle '''
    command_array = ["ffmpeg",
                     "-hide_banner",
                     "-loglevel", "error",
                     "-n",
                     "-i", file_path,
                    #  "-c",  "copy",  # <- problem
                     "-map", "0:s:{}".format(subtitle_index),
                     fileout_path]
    try:
        result = subprocess.run(command_array, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf8', check=False)
    except (UnicodeDecodeError, subprocess.CalledProcessError) as _e:
        return (-1, str(_e))
    return (result.returncode, result.stderr)



    


class ExtractSubtitles():
    ''' Extract subtitles from files '''

    def __init__(self, args):
        '''
        args : the ArgumentParser.parse_args()
        '''
        self.args = args
        self.supported_extensions = ['.mkv', '.mp4', '.mov', '.avi', '.mpg', '.mpeg']
        self.supported_codec = ['subrip', 'ass', ]
        self.unsupported_codec = ['hdmv_pgs_subtitle', 'dvd_subtitle']



    def get_ffmpeg_track_id(self, file_path):
        '''
        Returns the track ID of the SRT subtitles track
        '''
        # ffmpeg probe
        ffprobe_result = ffprobe(file_path=file_path)
        if ffprobe_result.return_code != 0:
            print('Error probe file "{}"'.format(file_path))
            print('  ', ffprobe_result.error, file=sys.stderr)
            return
        ffprobe_json = json.loads(ffprobe_result.json)
        fname_printed = False
        index_subtitle = -1
        streams_to_extract = []
        # keep only subtitle streams
        streams = [stream for stream in ffprobe_json.get("streams", []) if stream.get("codec_type", "unknown") == 'subtitle']
        if not streams and self.args.verbose > 1:
            print('No subtitles for "{}"'.format(file_path))
            return
        # examine streams
        for stream in streams:
            index_subtitle += 1
            index = stream.get("index", "unknown")
            codec_name = stream.get("codec_name", "unknown")
            if not fname_printed:
                print('Process "{}" for {} subtitle(s)'.format(file_path, len(streams)))
                fname_printed = True
            if self.args.show_probe:
                print('  ---> json subtitle {} :'.format(index_subtitle + 1))
                lines = json.dumps(stream, indent=4).splitlines()
                for line in lines:
                    print('  ', line)
            disposition = stream.get('disposition', {})
            forced = disposition.get('forced', 'unset')
            tags = stream.get('tags', {})
            language = tags.get('language', 'unset')    # found for french : "fre", "fra"
            title = tags.get('title', 'unset')
            is_forced = forced == 1 or 'forc' in title.lower()   # found : 'Forced', 'forced', '... Forcé', ...
            if self.args.verbose > 1:
                print('  ---> subtitle {} : stream_id:{}  -  subtitle_id:{}  -  codec:{}  -  language:{}  -   forced:{} ({})  -  title:{}  '.format(index_subtitle + 1, index, index_subtitle, codec_name, language, forced, is_forced, title))

            if self.args.scan_only:
                continue

            # ignore unsupported codec
            if codec_name in self.unsupported_codec:
                if self.args.verbose:
                    print('  ! Ignore unsupported stream "{}"'.format(codec_name))
                continue

            # ignore forced subtitles
            if is_forced:
                if not self.args.get_forced:
                    if self.args.verbose:
                        print('  ! Ignore stream forced')
                    continue

            # ignore language
            if language != 'unset':
                if language not in self.args.language.split(','):
                    if self.args.verbose:
                        print('  ! Ignore language "{}"'.format(language))
                    continue
            
            # ignore subtitles SDH
            if 'sdh' in title.lower() and not self.args.get_sdh:
                if self.args.verbose:
                    print('  ! Ignore stream SDH')
                continue

            # OK, this stream will be extracted
            streams_to_extract.append((index_subtitle, language, is_forced))

        # extract subtitles
        for index_subtitle, language, is_forced in streams_to_extract:
            foutname, _ = os.path.splitext(file_path)

            if len(streams_to_extract) == 1:
                final_name = '{}.srt'.format(foutname)
            else:
                final_name = '{}.{}.{}{}.srt'.format(foutname, language, index_subtitle, '.forced' if is_forced else '')
            if self.args.verbose > 1:
                print('  Subtitle filename : ', final_name)
            # never rewrite subtitles
            if os.path.exists(final_name):
                if self.args.verbose:
                    print('  ! Subtitles already exists ({})'.format(final_name))                             
                continue
            code, result = ffsubextract(file_path, index_subtitle, final_name)
            if code != 0:
                print('  !!! ERROR code {} : "{}"'.format(code, result))
            else:
                print('  extract done : ', final_name)



    def process_movie(self, root, name):
        ''' process movie '''
        if not root:
            root, name = os.path.split(name)
        (basename, ext) = os.path.splitext(name)
        if not ext in self.supported_extensions:
            return
        self.get_ffmpeg_track_id(os.path.join(root, name))


    def process(self):
        '''
        main entry
        '''
        for glob_name in self.args.filelist:
            glob_name = glob_name.rstrip("\r\n")
            for fname in glob.glob(glob_name):
                if os.path.isfile(fname):
                    self.process_movie(None, fname)
                elif os.path.isdir(fname):
                    # print('Parse directory', fname)
                    for root, _, files in os.walk(fname):
                        for fname in files:
                            self.process_movie(root, fname)



def main():
    '''
    Main entry
    '''

    parser = ArgumentParser(description='Extract subtitles from mkv files',
                                     formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument('filelist', nargs='+', help='files or directories to scan')
    parser.add_argument('-l', '--language', default='fre,fra', help='languages to extract, comma separated')
    parser.add_argument('-v', '--verbose', type=int, default=0, help='log verbosity')
    parser.add_argument('--get-sdh', action='store_true', help='get "Subtitles for the Dead and Hard of Hearing" (based on "SDH" in title attribute)')
    parser.add_argument('--get-forced', action='store_true', help='get "forced" subtitles (will use suffix "forced" in filename)')
    parser.add_argument('--show-probe', action='store_true', help='print ffprobe json results')
    parser.add_argument('--scan-only', action='store_true', help='scan files and exit')
    # parsing
    args = parser.parse_args()

    if not args.filelist:
        print("Error, need to specify directory or file  to parse")
        sys.exit(1)

    exsub = ExtractSubtitles(args)
    exsub.process()
    return

 

if __name__ == '__main__':
    # protect main from IOError occuring with a pipe command
    try:
        main()
    except IOError as _e:
        if _e.errno not in [22, 32]:
            raise _e
