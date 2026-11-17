# Surge 共用配置

`Surge_Rule.conf` 供新版 Surge Mac、iPhone 和 iPad 使用。策略组名称、顺序、默认项和规则优先级取自 `mihomo_smart/Proxy_Groups_Smart_Personal.yml`、`mihomo_smart/Rules_Smart_Personal.yml`；基础网络设置参考 `Clash/base.yaml`。

10 个地区组使用 Surge 原生 `smart`，以 `include-other-group` 导入订阅池中的实际代理节点，保留地区筛选、排除条件和 `policy-priority` 权重。业务组使用 `select`。 Surge 韩国组允许任意倍率节点，仍排除流量、到期等订阅信息；其他地区保留源模板的倍率筛选。原有 Surge 订阅入口、控制接口参数和 MITM 配置保留。Mihomo 的多个 `use` 订阅池不会自动变成 Surge 订阅；这里继续使用原有 Surge 订阅入口，也接受 `[Proxy]` 中手动添加的节点。

外部规则全部通过 `.list` 引用。上游已经提供 Surge 格式或兼容 classical `.list` 的规则直接引用，不生成副本；自定义 YAML、含 Surge 不支持类型的少数 GeoSite 清单和 Telegram 裸 IP 清单才转换到 `Clash/list/Surge/`。内容相同的转换结果共用一份文件。旧的 `Clash/list/` 文件不覆盖。`rule_sources.json` 记录转换来源和数量，供维护时检查，Surge 不读取该 JSON 或 YAML。

blackmatrix7 资源统一使用 `rule/Surge/`。Alibaba 和 GlobalMedia 的普通 `.list` 属于拆分版本，因此使用适合新版 Surge 的 `_All_No_Resolve.list` 完整版本，避免只加载规则集而漏掉配套域名集。

## SubConverter-Extended 转换

`SurgeRule.ini` 是 Surge 专用转换入口，使用 `surge_rule_base` 引用 `Surge_Rule.conf`，请求应指定 `target=surge&ver=5`。该模板面向 Extended，不用于 Stash 或 Surfboard。

后端会重建 `[Proxy Group]`，因此 INI 显式声明全部 77 个组：10 个原生 `smart` 地区组、66 个业务选择组和 1 个隐藏订阅池。通过 `[]` 原样传递 Surge 的筛选、权重、图标等字段；Smart 行末的测试地址和 `300` 仅满足转换器的输入解析格式，不会把输出改成 `url-test`，也不会设置 Surge Smart 的测试间隔。

转换模板关闭规则重建，保留底板中的 98 条 `.list` 分流规则和正则脚本。隐藏订阅池绑定本次请求的节点或订阅，不继承独立配置原有的订阅 URL。远程 `policy-path` 来源必须能由 Surge 读取；多个来源或服务端解析场景还取决于后端对输入格式的支持。

Surge 转换底板固定到已发布提交，生成器默认保留此版本并校验内容。`@main` 在不同 CDN 路径可能暂时返回不同版本，单次刷新成功不足以保证策略名称一致。更新时先发布底板，再用 `--base-ref <完整提交 SHA>` 生成并发布转换 INI；subweb-next 的 Surge 入口也引用该 INI 的完整提交，避免转换后端复用旧的分支模板缓存。

运行时模板、规则和脚本 URL 使用 `cdn.jsdelivr.net`；生成脚本的取源地址保留用于下载和审计。新增 INI、底板、脚本和清单需一起发布，CDN 才能读取新内容。

`subweb-next` 的模板入口按用户要求保留 `raw.githubusercontent.com` 直连：Surge 指向本目录的 `SurgeRule.ini`，Clash 的“自动选择”指向 `Clash/ClashRule_region_optional.ini`。Surge 入口仅在 Extended 后端显示，并显式使用转换格式 `ver=5`；Surfboard 保留独立的通用入口。

部署检查：若生成结果的 `#!MANAGED-CONFIG` 更新地址是 `http://127.0.0.1:25500/…`，需要在后端全局配置中将 `managed_config_prefix` 修正为公网入口（当前为 `https://api.miaoceo.com`）。该问题影响托管配置后续更新，不能通过本 INI 的 `surge_rule_base` 修正。

Surge 没有 `DOMAIN-REGEX` 类型，相关条件转换为 `.list` 中的 `SCRIPT` 条目，由 `scripts/domain-regex.js` 按原始正则精确检查主机名。需要启用 Surge 脚本功能；没有改成范围更大的域名关键词或通配符。上游原生 Surge 规则使用上游自己的平台适配内容，可能与其 Clash 版本的条数不同。

DNS 只使用 `[General]` 的全局设置，不生成 `[Host]` 或逐域名定向解析。H3 使用 Surge 的 `h3://`，同时保留 HTTPS 备选；DNSPod DoH 使用官方的 `doh.pub`。

Mihomo 的 nameserver-policy、GeoIP DNS fallback、客户端 ECS/ecs-override 和按规则集动态切换 fake-IP 没有移植；`always-real-ip` 仅保留明确可表达的主机名。LightGBM/collectdata/prefer-asn 等参数也不适用于 Surge 原生 Smart。

更新源模板后，在仓库根目录运行：

```powershell
python Surge/sync_from_mihomo.py
```

需要 Python 3.10+、PyYAML 和网络。脚本先下载、转换和校验全部输入，再写入配置及规则文件；源格式不支持时会报错，不会静默丢掉规则。新增 `.list` 和脚本需与配置一并推送，远程引用才可加载。

官方格式参考：[Smart](https://manual.nssurge.com/policy-groups/smart.html)、[策略导入](https://manual.nssurge.com/policy-groups/policy-including.html)、[外部规则](https://manual.nssurge.com/rules/ruleset.html)、[DNS](https://manual.nssurge.com/dns/local-dns-mapping.html)、[规则脚本](https://manual.nssurge.com/scripting/rule.html)。
