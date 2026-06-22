import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useHostTheme,
} from "cursor/canvas";

function Diagram() {
  const theme = useHostTheme();

  const box = (x: number, y: number, w: number, h: number, title: string, sub: string, tone: "accent" | "neutral" = "neutral") => {
    const fill = tone === "accent" ? theme.fill.secondary : theme.bg.elevated;
    const stroke = tone === "accent" ? theme.accent.primary : theme.stroke.primary;
    const titleColor = tone === "accent" ? theme.accent.primary : theme.text.primary;
    return (
      <g key={`${title}-${x}-${y}`}>
        <rect x={x} y={y} width={w} height={h} rx={10} fill={fill} stroke={stroke} />
        <text x={x + 14} y={y + 24} fontSize="13" fontWeight="600" fill={titleColor}>
          {title}
        </text>
        <text x={x + 14} y={y + 44} fontSize="11" fill={theme.text.secondary}>
          {sub}
        </text>
      </g>
    );
  };

  const arrow = (x1: number, y1: number, x2: number, y2: number, label?: string) => (
    <g key={`${x1}-${y1}-${x2}-${y2}-${label || ""}`}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={theme.stroke.primary} strokeWidth="1.5" />
      <polygon points={`${x2},${y2} ${x2 - 8},${y2 - 4} ${x2 - 8},${y2 + 4}`} fill={theme.stroke.primary} />
      {label ? (
        <text x={(x1 + x2) / 2 - 18} y={(y1 + y2) / 2 - 8} fontSize="10" fill={theme.text.tertiary}>
          {label}
        </text>
      ) : null}
    </g>
  );

  return (
    <div
      style={{
        border: `1px solid ${theme.stroke.primary}`,
        borderRadius: 12,
        padding: 12,
        background: theme.bg.editor,
      }}
    >
      <svg viewBox="0 0 1040 520" style={{ inlineSize: "100%", blockSize: "auto", display: "block" }}>
        {box(20, 40, 180, 72, "市场采集", "K线 / OI / 价格 / 交易所元数据")}
        {box(20, 148, 180, 72, "观察列表筛选", "定时筛选结果 -> 写库 + 发事件")}
        {box(20, 256, 180, 72, "规则检测", "命中规则 -> 生成 alert event")}
        {box(20, 364, 180, 72, "补数/富化", "市值 / OI价值 / 标签 / 模板")}

        {box(286, 84, 208, 96, "消息总线 / 中间件", "Kafka / RabbitMQ / Redis Streams", "accent")}
        {box(286, 252, 208, 96, "数据库", "Postgres 主存储 + Timeseries 可选", "accent")}

        {box(580, 40, 194, 72, "watchlist-writer", "消费筛选事件，落 watchlist_snapshot")}
        {box(580, 136, 194, 72, "rule-evaluator", "消费行情/观察列表，产出 alert_event")}
        {box(580, 232, 194, 72, "notification-worker", "消费告警事件，发 Discord/企微")}
        {box(580, 328, 194, 72, "query-api", "读库聚合，供 Web 面板查询")}

        {box(850, 88, 166, 72, "Web 面板", "只读 API，不依赖内存缓存")}
        {box(850, 232, 166, 72, "推送通道", "Discord / WeCom / 通用 Webhook")}

        {arrow(200, 76, 286, 132, "行情事件")}
        {arrow(200, 184, 286, 132, "筛选结果")}
        {arrow(200, 292, 286, 132, "规则输入")}
        {arrow(200, 400, 286, 132, "富化数据")}

        {arrow(494, 132, 580, 76, "消费")}
        {arrow(494, 132, 580, 172, "消费")}
        {arrow(494, 132, 580, 268, "消费")}

        {arrow(398, 180, 398, 252, "落库")}
        {arrow(774, 76, 286, 300, "快照回写")}
        {arrow(774, 172, 286, 300, "告警回写")}
        {arrow(774, 268, 286, 300, "发送结果回写")}
        {arrow(774, 364, 850, 124, "查询")}
        {arrow(774, 268, 850, 268, "发送")}
      </svg>
    </div>
  );
}

export default function MonitorArchitectureReview() {
  const theme = useHostTheme();

  return (
    <Stack gap={20}>
      <Stack gap={8}>
        <Row gap={8} align="center" wrap>
          <Pill tone="info" active>
            架构评审
          </Pill>
          <Pill>事件驱动</Pill>
          <Pill>解耦</Pill>
          <Pill>可替换推送</Pill>
        </Row>
        <H1>监控系统重构建议</H1>
        <Text tone="secondary">
          你的方向整体合理：把筛选、规则检测、推送、面板查询拆开，并以数据库和消息总线作为边界。更准确地说，应该追求
          “通过数据契约解耦”，而不是“脚本彼此完全不知道对方存在”。
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value="4" label="核心域服务" />
        <Stat value="2" label="基础设施组件" tone="info" />
        <Stat value="0" label="内存缓冲区依赖" tone="success" />
        <Stat value="1" label="推荐主数据库" />
      </Grid>

      <Callout tone="warning" title="先说结论">
        合理，但不要一上来拆成大量彼此毫无边界约束的小脚本。推荐把系统拆成少量独立服务，围绕统一事件模型和数据库表设计，
        而不是围绕“脚本文件”来设计。
      </Callout>

      <H2>推荐总体图</H2>
      <Diagram />

      <H2>我对你方案的判断</H2>
      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader trailing={<Pill tone="success" size="sm">保留</Pill>}>值得保留</CardHeader>
          <CardBody>
            <Stack gap={10}>
              <Text>筛选观察列表、规则检测、推送执行，这三类职责分离是对的。</Text>
              <Text>用数据库代替内存缓冲区，让面板和推送结果可追溯，也是对的。</Text>
              <Text>用消息中间件做异步解耦，可以避免一个模块卡死拖垮全链路。</Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="warning" size="sm">收敛</Pill>}>需要收敛</CardHeader>
          <CardBody>
            <Stack gap={10}>
              <Text>“各个脚本之间毫无关系”这句话不建议字面执行。业务上它们必须共享统一事件格式、统一主键、统一时钟语义。</Text>
              <Text>如果每个脚本各写各的表、各定各的字段，最终会从代码耦合变成数据耦合失控。</Text>
              <Text>“取消缓冲区”没有问题，但要用数据库里的 `alert_event` 和 `delivery_attempt` 替代，不要丢掉最近事件视图。</Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <H2>推荐组件</H2>
      <Table
        headers={["层", "推荐组件", "为什么", "是否必须"]}
        rows={[
          ["主数据库", "PostgreSQL", "关系清晰，事务可靠，后续可加分区/Timescale", "必须"],
          ["消息中间件", "RabbitMQ 或 Redis Streams", "先降低复杂度；吞吐不大时够用", "建议"],
          ["高吞吐总线", "Kafka", "只有在事件量大、回放需求强时再上", "可后置"],
          ["任务调度", "APScheduler / cron / 独立 scheduler", "统一定时触发采集与筛选", "必须"],
          ["Web API", "FastAPI", "读库聚合和管理接口都合适", "建议"],
          ["推送执行", "独立 worker", "隔离外部网络失败、限流、重试", "必须"],
        ]}
      />

      <H2>建议的服务边界</H2>
      <Table
        headers={["服务", "输入", "输出", "是否直接互调", "说明"]}
        rows={[
          ["market-ingestor", "交易所 API", "market_ticks / bars / oi snapshots", "否", "只负责采集与标准化"],
          ["watchlist-selector", "市场快照", "watchlist_snapshot + watchlist.updated", "否", "只负责筛选，不发通知"],
          ["rule-engine", "市场快照 + watchlist_snapshot", "alert_event", "否", "只负责判定命中"],
          ["notification-worker", "alert_event", "delivery_attempt / delivery_result", "否", "只负责发送和重试"],
          ["query-api", "数据库", "面板查询接口", "否", "只读聚合，替代当前内存 recent buffer"],
        ]}
      />

      <H2>关键表设计</H2>
      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>核心表</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>`instrument_snapshot`：最新标的行情快照</Text>
              <Text>`watchlist_snapshot`：当前观察列表状态</Text>
              <Text>`watchlist_reason_history`：入列原因变化</Text>
              <Text>`alert_event`：规则命中事实表</Text>
              <Text>`delivery_attempt`：每个通道的发送尝试与结果</Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>关键约束</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>每个事件都要有稳定 `event_id`。</Text>
              <Text>发送记录必须带 `channel`、`status`、`attempt_no`、`error_message`。</Text>
              <Text>观察列表快照和历史要分开，避免当前状态表越积越乱。</Text>
              <Text>把“今日第几次推送”改成数据库聚合，不再依赖进程内计数。</Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Divider />

      <H2>推荐落地顺序</H2>
      <Table
        headers={["阶段", "目标", "先不要做的事"]}
        rows={[
          ["Phase 1", "先引入 Postgres，把 watchlist / alert / delivery 落库", "先别上 Kafka"],
          ["Phase 2", "拆出 notification-worker 和 query-api", "先别做过度微服务化"],
          ["Phase 3", "把筛选器和规则引擎变成独立进程，通过 DB + 简单队列协作", "先别追求完全实时"],
          ["Phase 4", "当吞吐和回放需求明显增加时，再评估 Kafka / Timescale", "不要过早复杂化"],
        ]}
      />

      <Callout tone="info" title="我最推荐的架构">
        不是“一堆互不认识的脚本”，而是
        <Text as="span" weight="semibold"> 模块化单体向事件驱动逐步演进 </Text>
        ：先统一数据模型，先上 Postgres，再补一个轻量消息队列和两个独立 worker。这样风险最低，收益最大。
      </Callout>

      <Stack gap={6}>
        <H3>一句话建议</H3>
        <Text style={{ color: theme.text.secondary }}>
          如果你现在的数据量和并发都不算夸张，首选
          <Text as="span" weight="semibold"> PostgreSQL + RabbitMQ/Redis Streams + FastAPI + 独立 notification worker </Text>
          ，而不是直接上全套重型微服务。
        </Text>
      </Stack>
    </Stack>
  );
}
