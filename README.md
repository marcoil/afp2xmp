afp2xmp.py
==========

Convert from Corel AfterShot Pro XMP to standard XMP.

Usage
-----
<pre>
afp2xmp.py [-h] [-o OUTPUT] [-p] [-r] input

positional arguments:
  input                 The AfterShot Pro XMP file to read, or the directory to look in.

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        File to write result to. If not set, rewrite the input file.
                            Some markers are substituted:
                            {d}: The input file directory
                            {f}: The full input file name
                            {o}: The original image file name
                            {n}: The original image file name without extension
                            {e}: The original image file extension
                            The .xmp extension is added if not present.
  -p, --preserve        Preserve the output file's timestamps.
  -r, --recursive       Operate over all files in input directory and subdirectories.
</pre>

Examples
--------

    afp2xmp.py dsc09999.raw.xmp

Add standard XMP data into dsc09999.raw.xmp.

    afp2xmp.py -p dsc09999.raw.xmp

The same, but preserving the file timestamps.

    afp2xmp.py -o {e} dsc09999.raw.xmp

Extract the XMP data to dsc09999.xmp.

    afp2xmp.py -r /home/photog/RAW/

Add standard XMP data to all XMP files in /home/photog/RAW and its
subdirectories.

    afp2xmp.py -r -o {d}/xmps/{f} /home/photog/RAW/

Extract the data from all XMP files in /home/photog/RAW and its subdirectories
into XMP files in /home/photog/RAW/xmps/, keeping the subdirectory structure and
file names.
