# PDF Designer Skill

## Purpose
将终稿 Markdown 转为可读性高的 PDF，保证标题层级、段落间距和链接可读。

## Use this skill when
- 最终交付需要 PDF 附件。

## Do not use this skill when
- 只需文本输出，无需文件导出。

## Core rules
- 保留标题层级（H1/H2/H3）。
- 保留正文段落和必要留白。
- 对列表、引用、代码块提供可区分样式。
- 导出后必须检查是否可打开且内容不缺失。

## Standard workflow
1. 读取 markdown。
2. 映射样式并分页。
3. 生成 PDF。
4. 验证页数、链接文本、段落完整性。

## Output requirements
- 返回 PDF 文件路径
- 简述渲染是否完整
