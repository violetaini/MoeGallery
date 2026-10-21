# 可选的 Chitanda 统一登录

生产画廊已接入 Chitanda SSO。打开 `/login` 后进入统一账号授权，账号、密码和两步验证在 `https://sso.chitanda.net/portal` 维护。图库原有昵称、头像、图片和 API Key 保留。

生产通过专用 systemd 环境文件配置：

```ini
AGMS_AUTH_MODE=sso
AGMS_SSO_AGENT_URL=http://127.0.0.1:9788
AGMS_SSO_AGENT_KEY=填写本应用的随机内部凭据
```

本机认证代理来自独立私有仓库 `violetaini/chitanda-sso` 的 `clients/node`，不同应用凭据独立；精确回调为 `https://anime.chitanda.net/api/auth/sso/callback`。代理负责 OIDC、PKCE、state、nonce、签名、固定管理员身份和统一会话检查，OIDC 令牌不进入浏览器。

SSO 模式关闭原密码登录和本地认证密钥轮换，不在代理故障时回退。应用会话采用 Secure、HttpOnly、Host-only Cookie；写操作验证 Origin 和会话 CSRF，读有效性缓存最多五秒。退出统一账号会撤销相关应用访问。API Key 继续沿用各自权限和有效期。

没有配置该模式时，原有自建账号功能继续工作。环境文件由 systemd 读取，需 0600；真实密钥、数据库与账号资料不能提交 Git。集成测试见 `backend/tests/test_sso_integration.py`，原 API Key 与权限测试继续保留。
