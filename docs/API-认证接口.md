# 认证接口 (Auth API)

Base URL: `/api/auth`
uv run uvicorn app.main:app --port 8000 --reload
---

## 1. POST /register — 用户注册

创建新用户账号，返回 JWT access_token。

**请求体** `application/json`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `username` | string | 是 | 用户名，1-64 字符 |
| `identifier` | string | 是 | 登录标识（邮箱），3-128 字符，全局唯一 |
| `password` | string | 是 | 密码，6-128 字符 |
| `confirm_password` | string | 是 | 确认密码，须与 password 一致 |

**响应** `201 Created`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "auth_type": "password",
  "user": {
    "uid": "4c1a6f86-2352-49dd-bff7-9ba0f6ba5d03",
    "username": "测试用户",
    "identifier": "test@example.com",
    "provider": "password",
    "is_active": true,
    "created_at": "2026-05-30T16:30:10.302710",
    "last_login_at": null
  }
}
```

**错误码**

| 状态码 | detail | 说明 |
|---|---|---|
| 409 | 账号已存在 | identifier 重复 |
| 422 | 两次输入的密码不一致 | confirm_password 校验失败 |

---

## 2. POST /login — 用户登录

使用 identifier + password 登录，返回 JWT access_token。

**请求体** `application/json`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `account` | string | 是 | 登录标识（注册时填的 identifier） |
| `password` | string | 是 | 密码 |

**响应** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "auth_type": "password",
  "user": {
    "uid": "4c1a6f86-2352-49dd-bff7-9ba0f6ba5d03",
    "username": "测试用户",
    "identifier": "test@example.com",
    "provider": "password",
    "is_active": true,
    "created_at": "2026-05-30T16:30:10.302710",
    "last_login_at": "2026-05-30T16:30:10.496831"
  }
}
```

**错误码**

| 状态码 | detail | 说明 |
|---|---|---|
| 401 | 账号或密码不正确 | 账号不存在或密码错误 |

---

## 3. POST /oauth/mock — OAuth 模拟登录

开发阶段用的模拟 OAuth 登录，接受 QQ/学习通 provider。

**请求体** `application/json`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `provider` | string | 是 | `"qq"` 或 `"xuexitong"` |
| `authorization_code` | string | 是 | 模拟授权码，4-64 字符 |

**响应** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "auth_type": "oauth",
  "user": {
    "uid": "...",
    "username": "学习伙伴",
    "identifier": "xuexitong-learner@mock.local",
    "provider": "xuexitong",
    "is_active": true,
    "created_at": "...",
    "last_login_at": null
  }
}
```

---

## 4. GET /me — 获取当前用户

验证 JWT token 有效性，返回当前登录用户信息。**需要鉴权**。

**请求头**

```
Authorization: Bearer <access_token>
```

**响应** `200 OK`

```json
{
  "uid": "4c1a6f86-2352-49dd-bff7-9ba0f6ba5d03",
  "username": "测试用户",
  "identifier": "test@example.com",
  "provider": "password",
  "is_active": true,
  "created_at": "2026-05-30T16:30:10.302710",
  "last_login_at": "2026-05-30T16:30:10.496831"
}
```

**错误码**

| 状态码 | detail | 说明 |
|---|---|---|
| 401 | 无效的认证凭证 | Token 缺失/过期/格式错误 |
| 401 | 用户不存在 | Token 中的 uid 在数据库中找不到 |
| 403 | 账号已被禁用 | 用户 is_active=false |

---

## Token 说明

- 算法: HS256
- 过期时间: 2 小时
- 签名密钥: 环境变量 `JWT_SECRET`，默认值为开发密钥
- Token payload 结构: `{ "sub": "<uid>", "exp": <unix_timestamp> }`
