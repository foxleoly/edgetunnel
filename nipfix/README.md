# edgetunnel 在线优选 NIP 修复包 (nipfix)

## 背景
cmliu edgetunnel 的「在线优选」页 (/bestip) 依赖 `*.nip.lfree.org`（动态 DNS：
`<8位hex>.nip.lfree.org` 解析成对应 CF IP，且该域名挂 CF 泛证书，浏览器可直连 CF IP 读
`/cdn-cgi/trace` 的 `colo=`）。**2026-11 起 lfree 服务宕机**（DNS 无解析 + CF 边缘 TLS
handshake failure），导致在线优选「有效IP = 0」。nip.io / sslip.io 等公共替代只做 DNS、
没挂 CF，TLS 同样失败，不可用。

## 本包内容
| 文件 | 说明 |
|---|---|
| `nip_dns.py` | 纯 Python(stdlib) nip 风格权威 DNS 服务器。`<8位hex>.<ZONE>` → A 记录（hex 解码为 IPv4）。zone 外回 REFUSED，zone 内非 hex 名回 NXDOMAIN。已单测。 |
| `bestip_patched.html` | 补丁版在线优选页：① nip 域名可配置（页面输入框 + localStorage）② 新增「🔗 测试NIP连通性」按钮（1 秒判定当前 nip 域名通不通，避免再跑 10 分钟出 0 有效）③ 默认值仍是 nip.lfree.org（它恢复后无需改动）。已做浏览器功能验证 + JS 语法检查。 |

## 部署三步

### 1. 跑 nip DNS 服务（nip_dns.py）
需要**公网可达**的机器（手机 4G 也要测优选的话必须公网）：
```bash
# 生产 (systemd 或 docker)
NIP_ZONE=nip.你的域名.com NIP_PORT=53 python3 /path/to/nip_dns.py
```
- 开发/验证可用 NIP_PORT=5353（53 需 root 或 CapNet）。
- 日志格式：`[HH:MM:SS] <hex>.<zone> -> <ip>`。

### 2. 域名接 CF（CNAME 模式）
- 域名 `你的域名` 加进 CF 账号，选 **CNAME setup**（保留原 NS，CF 只管代理+证书）。
  - apex CNAME 指向跑 nip_dns 的机器（公网 hostname 或 IP，CF 支持 CNAME-flattening 到 IP）。
- CNAME setup 下 CF 自动为该 zone 各子域名签发 Universal SSL（`*.你的域名` 覆盖），
  于是浏览器 SNI `<hex>.你的域名` 在所有 CF IP 上都能完成 TLS。
- 验证（等 15-60 分钟）：
  ```bash
  dig @1.1.1.1 ac40e5bb.你的域名.com +short        # 应返回 172.64.229.187
  curl --resolve "ac40e5bb.你的域名.com:443:172.64.229.187" \
       https://ac40e5bb.你的域名.com/cdn-cgi/trace  # 应看到 colo= 行
  ```

### 3. 换 Pages 前端
- 把 edgetunnel Pages 变体的 `bestip.html` 替换为本包 `bestip_patched.html`，重新上传部署
  （CF Pages → 创建新部署）。
- 打开 `/bestip` 页：NIP域名 输入框填 `你的域名.com`（不带 `<hex>.` 前缀，不带协议），
  点「🔗 测试NIP连通性」→ 绿字 ✅ 即可正常跑在线优选。
- 该设置存 localStorage，每台设备首次填一次。

## 注意
- 在线优选只在 **CN 直连环境**有意义（CF 对非 CN 出口按最近 colo 路由，优选无收益）；
  cmliu 原版页面也内置了这个限制。
- nip_dns 只服务 `<8位hex>` 一个层级的名字；别把有正经子域名的 zone 拿来当 nip zone，
  建议用一个独立域名（便宜的 .xyz/.link 一年几十块）。
- 若 lfree 将来恢复，默认值不用改，直接可用。
