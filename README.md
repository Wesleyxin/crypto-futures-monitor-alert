# Crypto Futures Monitor Alert

币安 U 本位合约观察列表与告警工具。

当前版本已经做过轻量化，运行逻辑只保留：

- 观察列表自动筛选与手动维护
- 三条观察列表告警规则
- Web 看板
- 企业微信机器人推送
- Discord Embed 卡片推送

## 当前功能

### 观察列表入列规则

- 7 日 OI 涨幅 Top N
- 单日 OI 涨幅超过阈值
- 单日价格涨幅超过阈值
- 单日 OI 跌幅超过阈值
- 支持 Web 端手动添加 / 移除

### 当前仅保留的告警规则

- `price_oi_since_watchlist_high`
  - 持仓量和价格同时突破加入观察列表以来的最高点
  - 冷却时间 30 分钟

- `price_oi_rolling_7d_high`
  - 持仓量和价格同时突破 7 日滚动高点
  - 走全局冷却时间，当前默认 15 分钟

- `volume_spike_10m`
  - 10m 成交量涨幅超过 1000%
  - `10m` 由两个已收盘 `5m` bar 合成，并与前一个 `10m` 窗口比较
  - 走全局冷却时间，当前默认 15 分钟

### 内置看板

- 观察列表详情
- 最近告警列表
- 规则开关
- 手动添加 / 移除观察列表代币
- 告警提示音开关

## 环境要求

- Python `>= 3.8`
- 建议使用虚拟环境
- 需要能够访问：
  - Binance REST 接口
  - CoinGecko（如果启用市值功能）
  - 企业微信机器人 Webhook（如果启用推送）

## 安装

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

如果你已经有现成环境，也可以只执行：

```bash
pip install -r requirements.txt
pip install -e .
```

## 配置

主配置文件是：

- `config.yaml`

当前默认关键配置如下：

- `binance.restBaseUrl`
  - REST 数据源地址
- `watchlist.oi7d.topN`
  - 7 日 OI 涨幅榜入列数量
- `watchlist.oi1dUp.minPct`
  - 单日 OI 涨幅入列阈值
- `watchlist.price1dUp.minPct`
  - 单日价格涨幅入列阈值
- `watchlist.oi1dDown.maxPct`
  - 单日 OI 跌幅入列阈值
- `watchlist.retainDays`
  - 观察列表保留天数
- `watchlist.scanIntervalSec`
  - 观察列表扫描周期，当前默认 `300` 秒
- `alert.cooldownSec`
  - 通用规则冷却时间，当前默认 `900` 秒
- `alert.wecomWebhookUrl`
  - 企业微信群机器人 Webhook
- `alert.discordWebhookUrl`
  - Discord Webhook，使用 Embed 卡片格式推送
- `ui.enabled`
  - 是否开启 Web 看板
- `ui.host`
  - Web 看板监听地址
- `ui.port`
  - Web 看板端口，当前默认 `8767`
- `ui.authToken`
  - 看板和 `/api/*` 的访问令牌
- `ui.ruleToggleStorePath`
  - 规则开关持久化文件
- `watchlist.manualStorePath`
  - 手动观察列表持久化文件
- `altPollIntervalSec`
  - 告警检测轮询周期，当前默认 `45` 秒

## 启动

### 方式一：使用脚本

```bash
./run.sh
```

### 方式二：直接运行模块

```bash
python3 -m crypto_futures_monitor
```

### 指定配置文件

```bash
python3 -m crypto_futures_monitor /绝对路径/config.yaml
```

或者：

```bash
MONITOR_CONFIG=/绝对路径/config.yaml python3 -m crypto_futures_monitor
```

## 访问看板

默认端口：

```text
http://127.0.0.1:8767/
```

如果配置了 `ui.authToken`，需要带上 `token`：

```text
http://127.0.0.1:8767/?token=你的token
```

当前健康检查接口：

```text
/api/health
```

主要接口：

- `GET /api/alerts`
- `GET /api/watchlist`
- `GET /api/rule-toggles`
- `POST /api/rule-toggles/{rule_type}`
- `POST /api/watchlist/manual`
- `DELETE /api/watchlist/manual/{symbol}`

## 服务器部署教程

以下示例以你的服务器系统为准：

- `CentOS Linux release 8.5.2111`

建议部署方式：

- Python 虚拟环境
- 前期先用 `nohup` 跑通
- 稳定后再切到 `systemd`

### 1. 安装基础环境

```bash
sudo dnf install -y python38 python38-pip git
sudo dnf install -y python38-devel
```

检查版本：

```bash
python3 --version
```

项目要求：

- Python `>= 3.8`

### 2. 上传项目

把整个项目目录上传到服务器，例如：

```bash
/home/yourname/crypto-futures-monitor-alert
```

### 3. 创建虚拟环境并安装依赖

```bash
cd /home/yourname/crypto-futures-monitor-alert
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

如果你的系统里 `python3` 不是 3.8，也可以改成：

```bash
python3.8 -m venv .venv
```

### 4. 修改配置文件

编辑：

```bash
vim config.yaml
```

至少确认这些配置：

- `binance.restBaseUrl`
- `alert.wecomWebhookUrl`
- `ui.enabled`
- `ui.host`
- `ui.port`
- `ui.authToken`

如果你只打算用企业微信推送，确保：

- `alert.discordWebhookUrl: ""`

### 5. 前台启动测试

先不要急着后台常驻，先前台跑一次确认没有报错：

```bash
cd /home/yourname/crypto-futures-monitor-alert
source .venv/bin/activate
./run.sh
```

如果启动正常，日志里通常会看到：

- `REST 连通性检查通过`
- `可视化看板: http://0.0.0.0:8767/`

### 6. 后台运行（临时方案）

如果只是先让它在服务器上跑起来，可以用：

```bash
cd /home/yourname/crypto-futures-monitor-alert
source .venv/bin/activate
nohup ./.venv/bin/python3 -m crypto_futures_monitor > monitor.log 2>&1 &
```

查看进程：

```bash
ps -ef | grep crypto_futures_monitor
```

查看日志：

```bash
tail -f monitor.log
```

### 7. 放行面板端口

如果你要从外部浏览器访问看板，需要开放 `8767` 端口。

CentOS 8 一般用 `firewalld`：

```bash
sudo firewall-cmd --permanent --add-port=8767/tcp
sudo firewall-cmd --reload
```

然后浏览器访问：

```text
http://你的服务器IP:8767/?token=你的token
```

### 8. 开机自启（推荐）

长期运行建议用 `systemd`。

新建服务文件：

```bash
sudo vim /etc/systemd/system/crypto-futures-monitor.service
```

写入：

```ini
[Unit]
Description=Crypto Futures Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/yourname/crypto-futures-monitor-alert
ExecStart=/home/yourname/crypto-futures-monitor-alert/.venv/bin/python3 -m crypto_futures_monitor
Restart=always
RestartSec=5
User=yourname
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable crypto-futures-monitor
sudo systemctl start crypto-futures-monitor
```

查看状态：

```bash
sudo systemctl status crypto-futures-monitor
```

查看日志：

```bash
journalctl -u crypto-futures-monitor -f
```

### 9. 常用维护命令

重启服务：

```bash
sudo systemctl restart crypto-futures-monitor
```

停止服务：

```bash
sudo systemctl stop crypto-futures-monitor
```

禁用开机自启：

```bash
sudo systemctl disable crypto-futures-monitor
```

### 10. 部署前提醒

- `10m` 成交量规则已经按“最新已收盘 10m K 线 vs 前一根已收盘 10m K 线”修改过。
- 如果你服务器上只保留企业微信推送，建议把 `discordWebhookUrl` 保持为空。
- 首次部署后，建议先盯几分钟日志，确认：
  - REST 连通正常
  - 观察列表扫描正常
  - 看板端口正常监听
  - 企业微信推送没有报错

## 运行机制

### 1. 观察列表扫描

每 `watchlist.scanIntervalSec` 秒执行一次，当前默认：

```text
300 秒
```

执行内容：

- 拉取全市场 U 本位永续合约列表
- 计算 7 日 OI 涨幅
- 计算单日 OI 涨跌幅
- 计算单日价格涨幅
- 维护观察列表与入列原因

### 2. 告警检测

每 `altPollIntervalSec` 秒执行一次，当前默认：

```text
45 秒
```

执行内容：

- 遍历当前观察列表
- 检查“入列后价格 + OI 同时新高”
- 检查“7 日滚动价格 + OI 同时新高”
- 检查“10m 成交量涨幅是否超过 1000%”
- 满足条件后触发推送

### 3. 冷却与去重

- 全局冷却：`alert.cooldownSec`
- `price_oi_since_watchlist_high` 单独覆盖为 `30 分钟`
- 7 日滚动高点规则带数据边界去重，同一批 1h 数据不会重复推送

## 持久化文件

程序运行后会在项目目录生成或使用这些文件：

- `config.yaml`
  - 主配置
- `.monitor_manual_watchlist.json`
  - 手动观察列表
- `.monitor_rule_toggles.json`
  - 规则开关状态

## 当前规则开关文件示例

当前只保留三条规则开关：

- `price_oi_since_watchlist_high`
- `price_oi_rolling_7d_high`
- `volume_spike_10m`

## 推送说明

如果填写了对应配置，当前支持：

- 企业微信机器人推送
- Discord Embed 卡片推送

推送内容包含：

- 代币
- 价格
- OI 价值
- 市值
- 入列时间
- 入列原因
- 今日第几次推送
- 触发规则明细
- 告警时间

## 常用操作

### 查看当前进程日志

如果你是前台运行：

```bash
./run.sh
```

日志会直接输出到终端。

### 重启

如果已有旧进程占用了端口，可先查端口再停止：

```bash
lsof -nP -iTCP:8767 -sTCP:LISTEN
kill <PID>
./run.sh
```

### 检查服务是否正常

```bash
curl "http://127.0.0.1:8767/api/health"
```

返回应类似：

```json
{"status":"ok"}
```

## 项目结构

```text
crypto-futures-monitor-alert/
├── config.yaml
├── requirements.txt
├── run.sh
├── README.md
├── docs/
│   └── 需求说明.md
└── src/crypto_futures_monitor/
    ├── main.py
    ├── watchlist.py
    ├── alt_monitor.py
    ├── alerts.py
    ├── dashboard.py
    ├── alert_format.py
    ├── rule_toggles.py
    ├── coingecko.py
    ├── binance.py
    └── ...
```

## 说明

- `docs/需求说明.md` 是早期需求文档，不等于当前实际运行逻辑。
- 当前仓库以“轻量化后的实现”为准。
- 如果你后续再新增规则，建议同步更新本 README。
