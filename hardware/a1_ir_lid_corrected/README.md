# 第一版平盖｜镜像修正版

只替换原来的红外平盖，原底盒、主板固定和 USB-C/DC 开口均不改。修正 STL 的前后方向后，盖子真实翻面装配时，外侧文字正读，RESET 孔对准 USB-C 一端的主板按键。

- `a1-lid-v1-corrected.stl`：打印这个文件，外表面贴打印板，定位边和红外固定条朝上；单位 mm、缩放 100%，**不要再镜像**。
- `a1-lid-v1-corrected.scad`：可编辑源文件，默认装配预览；设 `part="lid"` 导出修正盖子。
- `a1-lid-v1-corrected-preview.png`：按真实旋转翻面生成的装配预览。

该盖子维持原来的 2.8 mm 盖顶、定位边和四个螺丝孔，沿用四颗 M3 × 8 mm 螺丝。红外板仍用 M2 × 5 mm。先将 RESET 孔对准板上按键，再装螺丝；打印和实物公差仍需试装。

交付 STL 为二进制格式。自行修改源文件后，建议用 OpenSCAD 命令行参数 `--export-format binstl -D 'part="lid"'` 重新导出，以保留坐标精度。

3.0 OLED 加高盖是另一种选择，见 [OLED 盖子](../a1_oled_enclosure/README.md)。两种盖子共用原来的 33 mm 高底盒，任选其一安装。
