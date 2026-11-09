# 快速开始

安装 Python 3.11 或更新版本，在项目根目录创建虚拟环境并安装：

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]' -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv/bin/resivent run cases/book/ch02/ex2-01.yaml --out build/results
.venv/bin/resivent serve
```

## 使用图形界面

首次使用需安装 Node.js 并在项目根目录构建本地资源：

```bash
cd web
npm ci --registry=https://registry.npmmirror.com --no-audit --no-fund
npm run build
cd ..
.venv/bin/resivent serve
```

在浏览器访问 `http://127.0.0.1:8765/`，选择全户新风量、户内压差、高层竖井或报告下载。逐项填写带单位的表单；卧室和装修材料的详细参数也可在下方算例编辑区修改，再点击“应用编辑”。点击计算后，展开“逐项参数来源分级”查看示例假设、用户改动和通用方法，核对软件版本与提交号。与内置示例相同的值保守标为“假设，需确认”，不同值标为“用户输入”；竖井未填写项列为模型通用默认值，结果页记录本次计算提交时的参数快照，并非参数实测认证。可导入、导出 JSON 或 YAML；报告页分别下载设计计算、竖井和验收运维文档。示例值须按实际情况更改，错误会显示字段路径及中文原因；气象和外部求解程序不随网页分发。

普通（非可编辑）安装请先完成上面的前端构建，再执行 `pip install .`，构建产物会打入 Python 包。服务依次使用 `ORV_WEB_DIR` 指定目录、安装包内资源和源码目录 `build/web`；三者均不存在时显示中文构建提示。源代码包若需携带界面，同样应先构建再打包。

本地页面采用内容安全策略，默认只允许同源资源与连接；组件运行时样式需要允许内联样式，图片允许本地数据 URI。此措施不是身份认证，禁止将无认证服务直接暴露到公网。

服务默认监听 `127.0.0.1:8765`，接口包括 `GET /modules`、`POST /run`、`POST /report`、`GET /rules`。默认无认证，请勿暴露到公网。输入数据短暂写入系统临时目录，请求完成后删除，不写入项目目录。算例参数需由设计者核实，程序结果不替代实际检测或安全评估。
