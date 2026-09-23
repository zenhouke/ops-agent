# Ops Agent 文档

项目文档 提供中英文操作指南、配置说明、部署与恢复步骤、可视化流程图，以及从当前后端路由生成的 Swagger / OpenAPI 接口参考。站点采用左侧分层目录、右侧正文，支持语言切换、全文搜索和移动端导航。

## 本地运行

需要 Docker Compose、Node/npm 和 Python 3。首次运行安装文档阅读器依赖，再启动文档容器：

```bash
npm ci --prefix wiki
npm run check --prefix wiki
npm run build --prefix wiki
docker compose -f wiki/compose.yaml up -d
```

文档容器与业务容器独立，支持挂载内容更新及页面自动刷新。访问地址在交付对话中提供。

## 更新 API 规范

在已安装项目后端依赖的环境中执行：

```bash
.venv/bin/python wiki/scripts/export_openapi.py
npm run check --prefix wiki
npm run build --prefix wiki
```

导出只加载路由和模型，使用临时隔离数据目录，不启动应用生命周期、不运行调度任务、不连接业务数据库。导出额外补充中间件认证、控制台手工解析的请求体和 SSE 响应类型。WebSocket 帧协议在文档中单独说明。

Swagger 使用本地资源且禁用请求执行；静态文档站不代理业务 API，也不保存访问令牌。

## 验证与维护

```bash
npm run check --prefix wiki
node --check wiki/assets/app.js
docker compose -f wiki/compose.yaml config --quiet
docker compose -f wiki/compose.yaml ps
```

内容变更应同步维护两种语言。检查涵盖本地资源、页内锚点、中英文内容和 OpenAPI 引用。静态构建、HTTP 检查、浏览器验收和真实运维操作验收需分别记录，不能互相替代。

停止文档服务：

```bash
docker compose -f wiki/compose.yaml down
```

# English

The documentation provides Chinese and English guides, configuration, deployment and recovery instructions, rendered flow diagrams and a generated Swagger / OpenAPI reference. It includes hierarchical navigation, language switching, full-text search and responsive navigation.

Use the commands above to install dependencies, validate, build and start the independent documentation container. Mounted content refreshes without restarting it. The access endpoint is supplied in the delivery conversation.

Regenerate the API specification after backend contract changes. Export uses isolated temporary data and does not start the application lifecycle or scheduler. Authentication, manually parsed console bodies and SSE types are supplemented; WebSocket frames are documented separately.

Swagger assets are served locally, request execution is disabled, and the documentation service stores no API credentials. Maintain both languages together and distinguish static checks, HTTP checks, browser validation and actual operational acceptance.
