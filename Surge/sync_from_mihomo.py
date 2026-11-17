"""Build the shared Surge profile and text rule sets from the personal templates.

Requires Python 3.10+, PyYAML. Network access is needed for upstream rules.
The private subscription and MITM settings are read from the existing profile.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "Surge/Surge_Rule.conf"
OUTPUT = ROOT / "Clash/list/Surge"
PUBLIC = "https://cdn.jsdelivr.net/gh/xuanranran/Clash@main/"
META = "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/"
NATIVE = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD",
    "IP-CIDR", "IP-CIDR6", "IP-ASN", "PROCESS-NAME", "USER-AGENT", "URL-REGEX",
}


def load(relative):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8-sig"))


def download(url):
    request = Request(url, headers={"User-Agent": "Clash-Surge-rule-sync/1.0"})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8-sig")


def quoted(value):
    # Current Surge profile syntax decodes escaped quotes and backslashes.
    return json.dumps(value, ensure_ascii=False)


def cdn_url(url):
    prefix = "https://raw.githubusercontent.com/"
    if not url.startswith(prefix):
        return url
    owner, repo, remainder = url[len(prefix):].split("/", 2)
    remainder = remainder.removeprefix("refs/heads/")
    ref, path = remainder.split("/", 1)
    return f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}"


def policy_options(body):
    """Split native Surge options without splitting commas in quoted regexes."""
    result, start, in_quotes, escaped = [], 0, False, False
    for index, character in enumerate(body):
        if escaped:
            escaped = False
        elif character == "\\" and in_quotes:
            escaped = True
        elif character == '"':
            in_quotes = not in_quotes
        elif character == "," and not in_quotes:
            result.append(body[start:index].strip())
            start = index + 1
    if in_quotes:
        raise ValueError("Unclosed quote in native Surge group")
    result.append(body[start:].strip())
    return result


def conversion_template(group_lines, base_ref="main"):
    output = [
        "; Surge only / SubConverter-Extended / target=surge&ver=5",
        "[custom]",
        "surge_rule_base=https://raw.githubusercontent.com/xuanranran/Clash/" + base_ref + "/Surge/Surge_Rule.conf",
        "; Preserve the native .list rules and rule scripts from the base profile.",
        "enable_rule_generator=false",
        "overwrite_original_rules=false",
        "append_proxy_type=false",
        "filter_deprecated_nodes=true",
        "udp_flag=true",
        "tcp_fast_open_flag=true",
        "",
        "; [] preserves native Surge options as literal fields during generation.",
        "; Smart's last two fields are parser placeholders, not url-test behavior.",
    ]
    for line in group_lines:
        name, body = line.split(" = ", 1)
        parts = policy_options(body)
        if name == "📥 订阅节点":
            # Bind to this conversion request, never the standalone profile's
            # pre-existing subscription URL. Remote inputs become policy-path;
            # parsed inline inputs become members of this same pool.
            output.append("custom_proxy_group=" + name
                          + "`select`.*`[]include-all-proxies=true`[]hidden=true")
            continue
        fields = ["custom_proxy_group=" + name, parts[0], *["[]" + x for x in parts[1:]]]
        if parts[0] == "smart":
            fields.extend(["https://www.gstatic.com/generate_204", "300"])
        output.append("`".join(fields))
    return "\n".join(output) + "\n"


def sections(text):
    result = {}
    section = None
    for line in text.splitlines():
        if re.fullmatch(r"\[[^]]+\]", line.strip()):
            section = line.strip()[1:-1]
            result[section] = []
        elif section is not None:
            result[section].append(line)
    return result


def sources(providers, base):
    result = {}
    for name, provider in providers.items():
        url = provider["url"]
        if "/gh/xuanranran/Clash@main/" in url:
            result[name] = {"local": url.split("/Clash@main/", 1)[1]}
        elif "/gh/blackmatrix7/" in url and name != "Alibaba_Classical_No_Resolve":
            result[name] = {"url": url.replace(
                "https://cdn.jsdelivr.net/gh/blackmatrix7/ios_rule_script@",
                "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/",
            ).replace("/rule/Clash/", "/rule/Surge/").removesuffix(".yaml") + ".list",
                "native": True}
            if name == "GlobalMedia":
                result[name]["url"] = result[name]["url"].removesuffix(".list") + "_All_No_Resolve.list"
        elif name == "Alibaba_Classical_No_Resolve":
            result[name] = {"url": "https://raw.githubusercontent.com/blackmatrix7/"
                            "ios_rule_script/master/rule/Surge/Alibaba/"
                            "Alibaba_All_No_Resolve.list", "native": True}
        elif "/MetaCubeX/" in url:
            url = url.replace("https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/", META)
            if url.endswith(".mrs"):
                url = url.replace("/geosite/", "/geosite/classical/").removesuffix(".mrs") + ".yaml"
            result[name] = {"url": url.removesuffix(".yaml") + ".list", "classical": True}
        elif "/ACL4SSR/" in url:
            result[name] = {"url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/"
                            "master/Clash/ProxyGFWlist.list", "native": True}
        else:
            raise ValueError(f"Unsupported provider: {name}")
    categories = {"private", "category-ads-all", "meta", "paypal", "linkedin", "vk",
                  "telegram", "cloudflare", "category-game-platforms-download", "cn",
                  "geolocation-!cn"}
    for name in sorted(categories):
        result["geosite-" + name] = {"url": META + "geo/geosite/classical/" + name + ".list", "classical": True}
    result["geoip-telegram"] = {"url": META + "geo/geoip/telegram.list", "cidrs": True}
    return result


def read_source(item, cache):
    name, source = item
    if "local" in source:
        lines = load(source["local"])["payload"]
    else:
        # Cache is a development convenience; downloaded inputs remain outside the repo.
        path = cache / (hashlib.sha256(source["url"].encode()).hexdigest() + ".txt") if cache else None
        try:
            text = path.read_text(encoding="utf-8-sig") if path and path.exists() else download(source["url"])
        except Exception as error:
            raise ValueError(f"Cannot load {name}: {source['url']}") from error
        if path and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if source.get("native") or source.get("classical") or source.get("cidrs"):
            lines = [line.strip() for line in text.splitlines()
                     if line.strip() and not line.lstrip().startswith(("#", ";", "//"))]
        else:
            lines = yaml.safe_load(text)["payload"]
    if source.get("cidrs"):
        lines = [("IP-CIDR6," if ":" in line else "IP-CIDR,") + line + ",no-resolve"
                 for line in lines]
    if not lines or not all(isinstance(line, str) for line in lines):
        raise ValueError(f"Empty or malformed source: {name}")
    return name, lines


def convert(name, lines, regexes):
    output = []
    inserted = False
    for original in lines:
        line = original.strip()
        kind, condition = line.split(",", 1)
        if kind == "DOMAIN-REGEX":
            re.compile(condition)
            regexes.setdefault(name, []).append(condition)
            if not inserted:
                output.append("SCRIPT,SurgeRegex_" + name.replace("@", "_").replace("!", "_"))
                inserted = True
            continue
        if kind not in NATIVE:
            raise ValueError(f"Unsupported rule in {name}: {kind}")
        if kind in ("IP-CIDR", "IP-CIDR6"):
            address, *options = condition.split(",")
            network = ipaddress.ip_network(address, strict=False)
            line = ",".join([kind, str(network), *options])
        output.append(line)
    return list(dict.fromkeys(output))


def dns_urls(values):
    if isinstance(values, str):
        values = [values]
    output = []
    for value in values:
        if value.startswith("rcode:"):
            continue
        url, _, fragment = value.partition("#")
        # DNSPod's public DoH endpoint; dns.pub is not the documented DoH hostname.
        url = url.replace("https://dns.pub/", "https://doh.pub/")
        if "h3=true" in fragment:
            output.append(url.replace("https://", "h3://", 1))
        output.append(url)
    return list(dict.fromkeys(output))


def host_patterns(lines):
    for line in lines:
        kind, condition = line.split(",", 1)
        if kind == "DOMAIN":
            yield condition
        elif kind == "DOMAIN-SUFFIX":
            yield condition
            yield "*." + condition
        elif kind == "DOMAIN-KEYWORD":
            yield "*" + condition + "*"
        elif kind == "DOMAIN-WILDCARD":
            yield condition


def generate(cache=None, base_ref=None):
    base = load("Clash/base.yaml")
    rules_template = load("mihomo_smart/Rules_Smart_Personal.yml")
    groups = load("mihomo_smart/Proxy_Groups_Smart_Personal.yml")["proxy-groups"]
    old = PROFILE.read_text(encoding="utf-8-sig")
    original = sections(old)
    paths = list(dict.fromkeys(re.findall(r"policy-path=(\"[^\"]+\"|[^,\s]+)", old)))
    if len(paths) != 1:
        raise ValueError("Expected one existing Surge subscription entry; preserve/resolve it before syncing")
    source_map = sources(rules_template["rule-providers"], base)
    with ThreadPoolExecutor(max_workers=10) as pool:
        entries = dict(pool.map(lambda item: read_source(item, cache), source_map.items()))
    needed = set()
    for rule in rules_template["rules"]:
        kind, condition, *_ = rule.split(",")
        if kind == "RULE-SET":
            needed.add(condition)
        elif kind == "GEOSITE":
            needed.add("geosite-" + condition.lower() if condition == "CN" else "geosite-" + condition)
        elif kind == "GEOIP" and condition == "telegram":
            needed.add("geoip-telegram")
    regexes, generated, urls, provenance, equivalent = {}, {}, {}, {}, {}
    for name, source in source_map.items():
        if source.get("classical"):
            # Existing classical .list resources can be read directly when all
            # entries use Surge rule types. Only incompatible sets need a copy.
            source["native"] = all(line.split(",", 1)[0] in NATIVE for line in entries[name])
        if name not in needed:
            provenance[name] = {**source, "dns_only": True, "entries": len(entries[name]),
                                "domain_regex_count": sum(l.startswith("DOMAIN-REGEX,") for l in entries[name])}
            continue
        signature = tuple(entries[name])
        if not source.get("native") and signature in equivalent:
            first = equivalent[signature]
            urls[name] = urls[first]
            provenance[name] = {**source, "surge_url": urls[name],
                                "entries": provenance[first]["entries"], "same_as": first,
                                "domain_regex_count": provenance[first]["domain_regex_count"]}
            continue
        output = convert(name, entries[name], regexes)
        if source.get("native"):
            urls[name] = cdn_url(source["url"])
        else:
            filename = name + ".list"
            # Provider names speedtest/Speedtest differ only in case. Only the former
            # is generated; the latter stays an upstream native Surge rule set.
            generated[filename] = "\n".join(output) + "\n"
            urls[name] = PUBLIC + "Clash/list/Surge/" + filename
            equivalent[signature] = name
        provenance[name] = {**source, "surge_url": urls[name], "entries": len(output),
                            "domain_regex_count": len(regexes.get(name, []))}
    assert len({n.casefold() for n in generated}) == len(generated)

    general = []
    updates = {
        "ipv6": "true" if base.get("ipv6") else "false",
        "ipv6-vif": "auto",
        "dns-server": ", ".join(base["dns"]["default-nameserver"]),
        "encrypted-dns-server": ", ".join(dns_urls(base["dns"]["nameserver"])),
        "encrypted-dns-follow-outbound-mode": "false",
        "encrypted-dns-skip-cert-verification": "false",
        "skip-proxy": "127.0.0.1, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, localhost, *.local",
        "internet-test-url": "https://www.gstatic.com/generate_204",
        "proxy-test-url": "https://www.gstatic.com/generate_204",
        "http-listen": "0.0.0.0:" + str(base["port"]),
        "socks5-listen": "0.0.0.0:" + str(base["socks-port"]),
        "wifi-access-http-port": str(base["port"]),
        "wifi-access-socks5-port": str(base["socks-port"]),
        "hijack-dns": "*:53",
    }
    real_ips = []
    for line in base["dns"]["fake-ip-filter"]:
        if not line.endswith(",real-ip"):
            continue
        rule = line.rsplit(",", 1)[0]
        kind = rule.split(",", 1)[0]
        if kind in {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-WILDCARD"}:
            real_ips.extend(host_patterns([rule]))
    updates["always-real-ip"] = ", ".join(dict.fromkeys(["localhost", "*.local", *real_ips]))
    for line in original["General"]:
        if not line.strip() or line.lstrip().startswith(("#", ";", "//")):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in {"vif-mode", "use-default-policy-if-wifi-not-primary"}:
            continue
        general.append(key + " = " + updates.pop(key, value.strip()))
    general.extend(key + " = " + value for key, value in updates.items())

    group_lines = []
    for group in groups:
        params = [group["type"]]
        if group["type"] == "smart":
            include = group.get("filter", ".*")
            exclude = group.get("exclude-filter", "")
            if group["name"] == "🇰🇷 韩国节点":
                # Surge permits Korean nodes at any multiplier; keep metadata exclusions.
                exclude = exclude.removesuffix(r"|(x([3-9]|\d{2,})|([3-9]|\d{2,})x)")
            if exclude.startswith("(?i)"):
                exclude = "(?i:" + exclude[4:] + ")"
            regex = ("^(?!.*(?:" + exclude + "))(?=.*(?:" + include + ")).*$"
                     if exclude else include)
            re.compile(regex)
            params += ["include-other-group=" + quoted("📥 订阅节点"),
                       "include-all-proxies=true", "policy-regex-filter=" + quoted(regex)]
            if "policy-priority" in group:
                params.append("policy-priority=" + quoted(group["policy-priority"]))
        else:
            params.extend(group.get("proxies", []))
            params += ["include-other-group=" + quoted("📥 订阅节点"), "include-all-proxies=true"]
        if group.get("hidden"):
            params.append("hidden=true")
        if group.get("icon"):
            params.append("icon-url=" + group["icon"])
        group_lines.append(group["name"] + " = " + ", ".join(params))
    group_lines.append("📥 订阅节点 = select, policy-path=" + paths[0] + ", update-interval=3600, hidden=true")

    rule_lines = []
    for rule in rules_template["rules"]:
        kind, condition, *rest = rule.split(",")
        if kind == "MATCH":
            rule_lines.append("FINAL," + condition)
        elif kind == "GEOSITE":
            rule_lines.append("RULE-SET," + urls["geosite-" + condition.lower() if condition == "CN" else "geosite-" + condition] + "," + ",".join(rest) + ",update-interval=86400")
        elif kind == "GEOIP" and condition == "private":
            rule_lines.append("RULE-SET,LAN," + ",".join(rest) + ",no-resolve")
        elif kind == "GEOIP" and condition == "telegram":
            rule_lines.append("RULE-SET," + urls["geoip-telegram"] + "," + ",".join(rest) + ",no-resolve,update-interval=86400")
        elif kind == "RULE-SET":
            rule_lines.append("RULE-SET," + urls[condition] + "," + ",".join(rest) + ",update-interval=86400")
        else:
            rule_lines.append(rule)

    scripts = ["SurgeRegex_" + name.replace("@", "_").replace("!", "_")
               + " = type=rule, script-path=" + PUBLIC + "Surge/scripts/domain-regex.js, argument="
               + quoted(name) for name in regexes]
    parts = ["# Mac / iPhone / iPad shared profile; native Surge Smart groups.",
             "# Rules and group order follow the personal Mihomo templates.",
             "[General]", *general, "", "[Proxy Group]", *group_lines,
             "", "[Rule]", *rule_lines,
             "", "[Script]", *scripts]
    for section, lines in original.items():
        if section not in {"General", "Proxy Group", "Rule", "Host", "Script"}:
            parts += ["", "[" + section + "]", *lines]
    profile = "\n".join(parts).rstrip() + "\n"
    if base_ref is None:
        template_path = ROOT / "Surge/SurgeRule.ini"
        previous = template_path.read_text(encoding="utf-8-sig") if template_path.exists() else ""
        match = re.search(r"^surge_rule_base=https://(?:raw\.githubusercontent\.com/xuanranran/Clash/|cdn\.jsdelivr\.net/gh/xuanranran/Clash@)([^/]+)/", previous, re.M)
        base_ref = match.group(1) if match else "main"
    if not re.fullmatch(r"main|[0-9a-f]{40}", base_ref):
        raise ValueError("--base-ref must be main or a full published commit SHA")
    if base_ref != "main":
        published = subprocess.check_output(
            ["git", "show", base_ref + ":Surge/Surge_Rule.conf"], cwd=ROOT
        ).decode("utf-8-sig").replace("\r\n", "\n")
        if published != profile:
            raise ValueError("Generated base differs from the pinned release. Use --base-ref main to prepare a new base, publish it, then rerun with --base-ref <published commit SHA>.")
    script = ('// Exact hostname regex rules converted from the personal rule sources.\n'
              'const patterns = ' + json.dumps(regexes, ensure_ascii=False, indent=2) + ';\n'
              'const host = String($request.hostname || "").toLowerCase().replace(/\\.$/, "");\n'
              'const expressions = patterns[String($argument || "")] || [];\n'
              '$done({matched: expressions.some(pattern => new RegExp(pattern).test(host))});\n')
    # Generate everything in memory before touching existing files.
    previous_manifest = ROOT / "Surge/rule_sources.json"
    previous_hashes = (json.loads(previous_manifest.read_text(encoding="utf-8")).get("generated_sha256", {})
                       if previous_manifest.exists() else {})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, content in generated.items():
        (OUTPUT / filename).write_text(content, encoding="utf-8", newline="\n")
    (ROOT / "Surge/scripts").mkdir(exist_ok=True)
    (ROOT / "Surge/scripts/domain-regex.js").write_text(script, encoding="utf-8", newline="\n")
    PROFILE.write_text(profile, encoding="utf-8", newline="\n")
    (ROOT / "Surge/SurgeRule.ini").write_text(conversion_template(group_lines, base_ref), encoding="utf-8", newline="\n")
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "groups": len(group_lines), "smart_groups": sum(g["type"] == "smart" for g in groups),
                "rules": len(rule_lines), "host_entries": 0,
                "dns_profile": "global", "sources": provenance,
                "dns_limitations": ["No Mihomo ECS/ecs-override or IP-dependent fallback translation",
                                    "No rule-set fake-IP switching; portable explicit always-real-ip only",
                                    "No full cn/geolocation DNS expansion on iOS; global DNS is the fallback",
                                    "DOMAIN-REGEX uses exact rule scripts for routing, not Host DNS matching"],
                "not_ported": ["Mihomo proxy-provider use membership; existing Surge subscription reused",
                               "Mihomo LightGBM/collectdata/sample-rate/prefer-asn/interval/lazy/max-failed-times"],
                "generated_sha256": {name: hashlib.sha256(content.encode()).hexdigest()
                                     for name, content in generated.items()}}
    (ROOT / "Surge/rule_sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Remove only obsolete files produced by the previous run, and only if their
    # bytes still match that run. Never remove independently edited rule files.
    for filename, digest in previous_hashes.items():
        path = (OUTPUT / filename).resolve()
        if (filename not in generated and path.parent == OUTPUT.resolve() and path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == digest):
            path.unlink()
    print(json.dumps({"groups": len(group_lines), "smart_groups": manifest["smart_groups"],
                      "rules": len(rule_lines), "generated_lists": len(generated),
                      "upstream_lists": sum(s.get("native", False) for name, s in source_map.items() if name in needed),
                      "regex_scripts": len(regexes), "host_entries": 0}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--base-ref", help="Published base commit SHA; existing pin is preserved by default")
    args = parser.parse_args()
    generate(args.cache_dir, args.base_ref)
