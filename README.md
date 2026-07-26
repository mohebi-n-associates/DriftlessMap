# HERBS
A Python-based GUI for Histological E-data Registration in Brain Space


HERBS is an open source, extensible, intuitive and interactive software platform for image visualisation and image registration. Where the image registration is the process of identifying a spatial transformation that maps images to a template such that corresponding anatomical structures are optimally aligned, or in other words, a voxel-wise ‘correspondence’ is established between the images and template.

HERBS 1.0.3 supports Python 3.10–3.14 and uses Qt 6 through PyQt6. Python
3.14 in a dedicated environment is recommended for new installations. For
details, see the HERBS CookBook or the latest tutorials.

HERBS provides users:

- 2D and 3D visualisation of brain atlas volume data and arbitrary slicing.
- Image registration with interactive local elastic deformation methods in current version.
- 2D and 3D visualisation of user defined data.

## Install

> **Note:** Until HERBS 1.0 is published to PyPI, install it from this source
> repository as shown below.

Install [Miniconda or Anaconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html), then create a dedicated environment named `HERBS` with Python 3.14:

```bash
conda create --name HERBS python=3.14 -y
conda activate HERBS
python --version
python -m pip install --upgrade pip
```

The version check should report Python 3.14. Clone this repository and install
HERBS while the `HERBS` environment is active:

```bash
git clone https://github.com/mohebi-n-associates/HERBS.git
cd HERBS
python -m pip install .
```

### Zeiss CZI files

CZI support uses the optional `aicspylibczi` package. Its prebuilt packages
currently support Python through 3.13, so use a Python 3.13 environment and
install the `czi` extra when you need to open CZI files:

```bash
conda create --name HERBS-CZI python=3.13 -y
conda activate HERBS-CZI
python -m pip install --upgrade pip
python -m pip install ".[czi]"
```

All other HERBS features work on Python 3.14 without this optional dependency.

Run `conda activate HERBS` again whenever you open a new terminal before launching or updating HERBS.

If you would like to modify the source code and have your changes take effect immediately (without reinstalling), use an editable install instead:

```bash
python -m pip install -e .
```

To upgrade to the newest version later, activate the same environment, pull the latest changes, and reinstall:

```bash
conda activate HERBS
git pull
python -m pip install . --upgrade
```

Please always use the newest version of HERBS.

See the cumulative [What’s New in HERBS](WhatsNew.md) history for release
details and upgrade notes.

<details>
<summary>Downloaded a ZIP instead of cloning?</summary>

Download the repository from GitHub (**Code → Download ZIP**), unzip it, then from a terminal:

```bash
conda activate HERBS
cd path/to/HERBS       # the unzipped folder containing setup.py
python -m pip install .
```
</details>

## Usage

```python
import herbs
herbs.run()
```

After running the above scripts, a GUI window will pop up. Users can download atlas and upload images for further process,

<img src="./herbs/herbs.png" width="800px"></img>

For more information, please read HERBS CookBook (on going) or check the Tutorial folder for corresponding functionalities.

## Atlas Storage

- <span style="font-weight:700;font-size:18px">
    Do not store Atlases inside HERBS folder. 
</span>
When downloading Atlases, HERBS asks users to select the folder to store the atlas. Please choose a folder other than HERBS folder.

- <span style="font-weight:700;font-size:18px">
    Save different Atlas in different folders. 
</span>
When downloading an atlas other than the one you already have, please store it in another folder.


## Some Pre-Requirement Issues

- In order to run HERBS properly, 64 bit operating systems and 64 bit Python are required.

- 3D visualisation in HERBS depends on OpenGL, if you face to the problem that no OpenGL is installed on your machine, please see (https://www.opengl.org) to download and install accordingly. 

- If you use MacOS and face to the problem of ImportError states that "Unable to load OpenGL package". Please try to find the OpenGL package folder from where you install all python packages in your enviroment, and go to OpenGL's child-folder "platform", open "ctypesloader.py", and change line 

```python
fullName = util.find_library( name )
```

to

```python
fullName = '/System/Library/Frameworks/OpenGL.framework/OpenGL'
```


- The recommended Conda command in the installation section installs the correct Python version inside the `HERBS` environment; a separate system-wide Python installation is not required.

- Conda includes **pip** in the environment. Use `python -m pip` as shown above so packages are installed into the active `HERBS` environment rather than another Python installation. You can confirm its location with `python -m pip --version`.

- Install and run HERBS in the dedicated Conda environment named `HERBS` described above to prevent dependency conflicts with other Python programs.

## Dependency issues

Use a fresh environment and let `python -m pip install .` resolve the compatible
NumPy, Numba, OpenCV, PyQt6, and pyqtgraph versions. Do not install PyQt5 into
the same environment: HERBS 1.0 is a Qt 6 application.

### 
Please report your issues: https://github.com/mohebi-n-associates/HERBS/issues. Please have a good description (maybe a screenshot or an error message). Any feedback welcome!

Please feel free to start any discussion: https://github.com/mohebi-n-associates/HERBS/discussions.

## Finally
HERBS is 'always' in development, please check updates every time before you use it.


Hope this tool makes your amazing research life more tasty :-)
