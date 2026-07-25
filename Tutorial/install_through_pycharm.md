## Install HERBS through PyCharm

This guide assumes Python 3.10–3.14 and a current PyCharm release. Python 3.14
is recommended, or Python 3.13 if Zeiss CZI support is required.

If PyCharm is not installed, please install PyCharm first through (https://www.jetbrains.com/pycharm/). For more details about how to install and set up PyCharm (https://www.jetbrains.com/help/pycharm/installation-guide.html). For example,

- Create a Python project (https://www.jetbrains.com/help/pycharm/creating-empty-project.html)

- Install, uninstall, and upgrade packages (https://www.jetbrains.com/help/pycharm/installing-uninstalling-and-upgrading-packages.html)


<table>
<tr>
<th align="center">
<img width="441" height="1">
<p> 
<small>
Steps
</small>
</p>
</th>
<th align="center">
<img width="441" height="1">
<p>
<small>
Results
</small>
</p>
</th>
</tr>
<tr>
<td>
-Go to Python Interpreter <br>
	**File | Settings | Project | Python Interpreter** for Windows and Linux <br>
	**PyCharm | Preferences | Project | Python Interpreter** for macOS
	
And press the **+** button.
</td>
<td align="center" width="40%">
<img src="../image/download_pycharm1.jpg" width="500">
</td>
</tr>
</tr>
<tr>
<td>
<ul>
<li>Clone the HERBS repository, open it as the PyCharm project, and select a
fresh Python 3.14 interpreter. In PyCharm's terminal, run
<code>python -m pip install -e .</code>. For CZI support with Python 3.13, run
<code>python -m pip install -e ".[czi]"</code>.
</li>
</ul>
</td>
<td align="center" width="40%">
<img src="../image/download_pycharm2.jpg" width="500">
</td>
</tr>

</table>
