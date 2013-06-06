#!/usr/bin/python
# -*- coding: utf-8 -*-

# ******************************************************************************
#
# Copyright (C) 2013 Marc Ordinas i Llopis <mail@marcoil.org>
#
# afp2xmp.py is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# afp2xmp.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with afp2xmp.py; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, 5th Floor, Boston, MA 02110-1301 USA.
#
# Author: Marc Ordinas i Llopis <mail@marcoil.org>
#
# ******************************************************************************

# ******************************************************************************
# Version and module checks, imports
# ******************************************************************************

import sys
if sys.version_info < (2, 7):
    print "This program needs Python 2.7 or later to work."

try:
    import pyexiv2
except ImportError:
    print "This program needs pyexiv2 to work, please install it and try again"
    exit()

import argparse
from fnmatch import fnmatch
from functools import partial, wraps
import multiprocessing
from os import makedirs, path, walk
import os
import re
import sys

# ******************************************************************************
# Substitution methods
# ******************************************************************************

# Retrieves the current value and tries to merge new values with it
def merge_tag_values(orig, value):
    if isinstance(orig, dict) and isinstance(value, dict):
        return orig.update(value)
    if isinstance(orig, list) and isinstance(value, list):
        return orig.extend(value)
    if isinstance(orig, list):
        return orig.append(value)
    return value

substitutions = []
def substitution(in_tag, out_tag, merge=False, convert=None):
    """A decorator for substitution functions."""
    afp_base = "Xmp.dmf.versions[1]/dmfversion:settings/bset:layers[1]/blay:options/bopt:"
    def decorator(func):
        @wraps(func)
        def wrapper(metadata, *args, **kwargs):
            in_tag_full = afp_base + in_tag
            try:
                value = metadata[in_tag_full].value
            except KeyError:
                # In tag not present, so do nothing
                return
            
            if convert:
                value = convert(value)
            
            result = func(value, *args, **kwargs)
            
            if merge:
                try:
                    orig = metadata[out_tag].value
                    result = merge_tag_values(orig, result)
                except KeyError:
                    # There was nothing there before, so just use the new value
                    pass
            
            metadata[out_tag] = result
        
        # Put all substitutions in a list
        substitutions.append(wrapper)
        return wrapper
    return decorator

def simple(value):
    return value

substitution('rating', 'Xmp.xmp.Rating', convert=int)(simple)
substitution('profilemake', 'Xmp.tiff.Make')(simple)
substitution('profilemodel', 'Xmp.tiff.Model')(simple)

def split_lang(value):
    lang, text = value.split('|')
    return {lang: text}

substitution('description', 'Xmp.dc.description')(split_lang)

def gpscoordinate(value):
    return pyexiv2.GPSCoordinate.from_string(value)

substitution('GPSLatitude', 'Xmp.exif.GPSLatitude')(gpscoordinate)
substitution('GPSLongitude', 'Xmp.exif.GPSLongitude')(gpscoordinate)

@substitution('keywordlist', 'Xmp.dc.subject', merge=True)
def subject_tags(value):
    return re.split(';|,', value)

# Very special case: hierarchicalSubject
# We need to do it this way because pyexiv2 does not support writing to
# Xmp.lr.hierarchicalSubject, or to directly use bags from python
def process_hierarchical_tags(metadata):
    lrhs = 'Xmp.lr.hierarchicalSubject'
    outtag = metadata[lrhs]
    tags = ''
    try:
        tags = metadata[AFP_BASE + 'keywordlist']
    except KeyError:
        # We have to delete the already existing hierarchical tags
        # if also empty
        if len(outtag.value) == 0:
            del(metadata[lrhs])
            return
    if len(tags) == 0:
        return
    taglist = tags.replace(';', '|').split(',')
    for tag in taglist:
        metadata[lrhs] = tag
# substitutions.append(hierarchical_tags)

# TODO: Make hierarchical tags work
# @substitution('keywordlist', 'Xmp.lr.hierarchicalSubject', merge=True)
# def hierarchical_tags(value):
#     return value.replace(';', '|').split(',')

# ******************************************************************************
# Functions
# ******************************************************************************

# Get all XMP files in all subdirectories
# Taken from http://stackoverflow.com/q/2186525/2110960
def walk_xmps(root):
    for dirpath, dirs, files in walk(root, followlinks=True):
        for basename in files:
            if fnmatch(basename, "*.xmp"):
                filename = path.join(dirpath, basename)
                yield filename

# Generate an output filename
def build_output_filename(output, filename):
    head, tail = path.split(filename)
    # If output is a dir, put the file there
    if output.endswith(os.sep):
        return path.join(output, tail)
    orig, xmp = path.splitext(tail)
    root, ext = path.splitext(orig)
    result = output.format(d=head, f=tail, o=orig, n=root, e=ext[1:])
    if not result.endswith('.xmp'):
        result = result + '.xmp'
    return result

# Create a new XMP file
# TODO: This is necessary because pyevix2 does not allow to create an empty XMP
# file, so a new one is needed

# An empty XMP file
empty_xmp = """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  </rdf:RDF>
</x:xmpmeta>
"""

def create_output_file(filename):
    # Ensure that the output directory exists
    out_dir = path.abspath(path.dirname(filename))
    if not path.isdir(out_dir):
        makedirs(out_dir)
    f = open(filename, 'w')
    f.write(empty_xmp)
    f.close

def process_xmp(filename, output=False, preserve=False):
    metadata = pyexiv2.ImageMetadata(filename)
    try:
        metadata.read()
    except IOError as e:
        return (False, filename, "Error reading metadata: " + e.message)
    
    out_metadata = metadata
    out_filename = filename
    if output is not False:
        out_filename = build_output_filename(output, filename)
        try:
            create_output_file(out_filename)
            out_metadata = pyexiv2.ImageMetadata(out_filename)
            out_metadata.read()
            metadata.copy(out_metadata, comment=False)
        except IOError as e:
            return (False, out_filename, "Error creating output: " + e.message)
    
    # Do all the processing
    for f in substitutions:
        try:
            f(out_metadata)
        except pyexiv2.XmpValueError as e:
            print "error: value {} type {}".format(e.value, e.type)
            return (False, out_filename, str(e))
    
    # Write back the data
    try:
        pass
        out_metadata.write(preserve_timestamps=preserve)
    except IOError as e:
        return (False, out_filename, "Error writing output: " + e.message)
    
    return (True, filename, out_filename)

# ******************************************************************************
# Main code
# ******************************************************************************
if __name__ == '__main__':
    argparser = argparse.ArgumentParser(
        description="Convert AfterShot Pro XMP data to standard XMP.",
        formatter_class=argparse.RawTextHelpFormatter)
    argparser.add_argument("input", help="The AfterShot Pro file to read.")
    args_output = argparser.add_mutually_exclusive_group()
    args_output.add_argument("-o", "--output", default=False,
        help="""File to write result to. If not set, rewrite the input file.
    Some markers are substituted:
    {d}: The input file directory
    {f}: The full input file name
    {o}: The original image file name
    {n}: The original image file name without extension
    {e}: The original image file extension
    The .xmp extension is added if not present.""")
    args_output.add_argument("-p", "--preserve", action="store_true", default=False,
        help="Preserve the output file's timestamps.")
    argparser.add_argument("-r", "--recursive", action="store_true", default=False,
        help="Operate over all files in input directory and subdirectories.")
    args = argparser.parse_args()

    # Check files exist, assign to inputs
    if args.recursive:
        if not path.isdir(args.input):
            print "Non-existent input directory {}".format(args.input)
            sys.exit(1)
        inputs = walk_xmps(args.input)
    else:
        if not path.isfile(args.input):
            print "Non-existent input file {}".format(args.input)
            sys.exit(1)
        inputs = [args.input]

    # Add the necessary namespaces
    pyexiv2.xmp.register_namespace("http://ns.adobe.com/lightroom/1.0/", "lr")
    
    # Use a multiprocessing pool
    pool = multiprocessing.Pool()
    results = pool.imap(
        partial(process_xmp, output=args.output, preserve=args.preserve),
        inputs)

    result = 0
    for r in results:
        if r[0] is True and args.output:
            print "File processed successfully: {} -> {}".format(r[1], r[2])
        elif r[0] is True:
            print "File processed successfully: {}".format(r[1])
        else:
            result = 1
            print "Error processing file {}: {}".format(r[1], r[2])

    sys.exit(result)

