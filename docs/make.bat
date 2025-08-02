:: docs/make.bat
:: 用于 Sphinx 文档的命令文件。
:: 经过优化，以支持扁平化的目录结构（无 "source" 子目录）。

@ECHO OFF

REM 将当前目录切换到批处理文件所在的目录，以确保路径正确
pushd %~dp0

REM 如果环境变量中没有定义 SPHINXBUILD，则使用默认值
if "%SPHINXBUILD%" == "" (
	set SPHINXBUILD=sphinx-build
)

REM --- 核心优化：定义源目录和构建目录 ---
set SOURCEDIR=.
set BUILDDIR=_build
set SPHINXOPTS=%*

REM 检查 sphinx-build 命令是否存在
%SPHINXBUILD% >NUL 2>NUL
if errorlevel 9009 (
	echo.
	echo [错误] 'sphinx-build' 命令未找到。
	echo.
	echo 请确保您已经安装了 Sphinx (例如：pip install -r requirements.txt)，
	echo 并且 'sphinx-build' 所在路径已添加到系统的 PATH 环境变量中。
	echo.
	echo 您可以从这里获取 Sphinx: https://www.sphinx-doc.org/
	echo.
	exit /b 1
)

REM 如果没有提供参数，则显示帮助信息
if "%1" == "" goto help

REM 将所有参数传递给 sphinx-build 的 "make-mode"
%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% %SPHINXOPTS%
goto end

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR% %SPHINXOPTS%

:end
popd