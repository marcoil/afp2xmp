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

import argparse
from fnmatch import fnmatch
from functools import partial, wraps
import multiprocessing
from os import makedirs, path, walk
import os
import re
from xml.dom import minidom

# ******************************************************************************
# Static data
# ******************************************************************************

afp_base = "Xmp.dmf.versions[1]/dmfversion:settings/bset:layers[1]/blay:options/bopt:"
namespaces = {
    'tiff': "http://ns.adobe.com/tiff/1.0/",
    'exif': "http://ns.adobe.com/exif/1.0/",
    'photoshop': "http://ns.adobe.com/photoshop/1.0/",
    'Iptc4xmpCore': "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/",
    'xmp': "http://ns.adobe.com/xap/1.0/",
    'dc': "http://purl.org/dc/elements/1.1/",
    'lr': "http://ns.adobe.com/lightroom/1.0/",
}

# ******************************************************************************
# Substitution methods
# ******************************************************************************

def convert_into_node(dom, tag, value):
    def create_li_node(text):
        linode = dom.createElement('rdf:li')
        linode.appendChild(dom.createTextNode(unicode(text)))
        return linode
    
    def create_sequence_node(tag, iterator):
        node = dom.createElement(tag)
        for i in iterator:
            node.appendChild(create_li_node(i))
        return node
    
    node = dom.createElement(tag)
    
    if isinstance(value, dict):
        # Use dicts like {"x-default": "Text"} for translations
        altnode = dom.createElement('rdf:Alt')
        for lang, text in value.items():
            linode = create_li_node(text)
            linode.setAttribute('xml:lang', unicode(lang))
            altnode.appendChild(linode)
        node.appendChild(altnode)
    elif isinstance(value, list):
        # Lists are converted to rdf:Bags
        node.appendChild(create_sequence_node('rdf:Bag', value))
    elif isinstance(value, tuple):
        # Tuples are converted to rdf:Seq
        node.appendChild(create_sequence_node('rdf:Seq', value))
    else:
        # Just convert to a text node
        node.appendChild(dom.createTextNode(unicode(value)))
    
    return node

transfers = []
def transfer(in_attrib, # The bopt attribute
             out_tag # If set, the tag of the Description child or attribute
             ):
    """A decorator for transfer functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(dom, desc, options):
            in_name = "bopt:" + in_attrib
            out_isattrib = True if out_tag.startswith('@') else False
            out_name = out_tag[1:] if out_isattrib else out_tag
            
            # Check the input attribute is present
            if not options.hasAttribute(in_name):
                return
            # Check the target isn't already present
            if out_isattrib and desc.hasAttribute(out_name):
                return
            if (not out_isattrib) and \
                    len(desc.getElementsByTagName(out_name)) > 0:
                return
            
            in_value = options.getAttribute(in_name)
            result = func(in_value)
            
            if not result:
                return
            
            # Now convert the result to something we can add to the tree
            # If it's a DOM Node, add it to rdf:Description
            if isinstance(result, minidom.Element):
                desc.appendChild(result)
            elif isinstance(result, minidom.Attr):
                desc.setAttributeNode(result)
            elif out_isattrib:
                desc.setAttribute(out_name, unicode(result))
            else:
                desc.appendChild(convert_into_node(dom, out_name, result))
        
        # Put all substitutions in a list
        transfers.append(wrapper)
        return wrapper
    return decorator

def simple(value):
    return value

transfer('rating', '@xmp:Rating')(simple)
transfer('profilemake', '@tiff:Make')(simple)
transfer('profilemodel', '@tiff:Model')(simple)
transfer('GPSLatitude', '@exif:GPSLatitude')(simple)
transfer('GPSLongitude', '@exif:GPSLongitude')(simple)

def split_lang(value):
    lang, text = value.split('|')
    return {lang: text}

transfer('description', 'dc:description')(split_lang)

@transfer('keywordlist', 'dc:subject')
def subject_tags(value):
    return re.split(';|,', value)

@transfer('keywordlist', 'lr:hierarchicalSubject')
def hierarchical_tags(value):
    return value.replace(';', '|').split(',')

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

def create_output_file(filename):
    # Ensure that the output directory exists
    out_dir = path.abspath(path.dirname(filename))
    if not path.isdir(out_dir):
        makedirs(out_dir)
    f = open(filename, 'w')
    return f

def process_xmp(filename, output=False, preserve=False):
    dom = None
    try:
        dom = minidom.parse(filename)
    except IOError as e:
        return (False, filename, "Error reading file: " + e.message)
    
    try:
        desc = dom.getElementsByTagName('rdf:Description')[0]
    except IndexError:
        return (False, filename, "Not a valid XMP file.")
    
    try:
        # We get the last one in case there are multiple versions
        options = dom.getElementsByTagName('blay:options')[-1]
    except IndexError:
        return (False, filename, "Not an AfterShot Pro XMP file.")
    
    # Add the necessary namespaces
    for ns, url in namespaces.items():
        desc.setAttribute('xmlns:'+ns, url)
    
    # Do all the processing
    for f in transfers:
        try:
            f(dom, desc, options)
        except Exception as e:
            return (False, filename, str(e))
    
    # Write back the data
    out_filename = filename
    if output is not False:
        out_filename = build_output_filename(output, filename)
    try:
        outf = create_output_file(out_filename)
        out = dom.toprettyxml(indent=' ', encoding='UTF-8')
        outf.write(out)
        outf.close()
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

