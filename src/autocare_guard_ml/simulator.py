"""数据模拟器：模拟售后服务事件持续发送研判请求到 /judge 接口。

启动方式:
    python -m autocare_guard_ml.simulator --interval 1 --port 8000

模拟逻辑:
    - 时间感知：深夜低谷、日间平稳、晚间高峰
    - 突发事件：随机触发「热安全告警集中」「充电异常批量上报」
    - 主题多样：动力电池、充电高压、制动转向、智驾、车机、重复维修等
    - 多证据：对话、车辆信号、故障码、服务历史
"""
from __future__ import annotations

import argparse
import asyncio
import math
import random
import time
from datetime import datetime

# ===== 售后对话与主题模板 =====

# 无风险 / 信息咨询
SAFE_CHATS = [
    "想问一下下次保养大概什么时候？里程快到了。",
    "车机导航能更新到最新地图吗？操作步骤发我一下。",
    "质保手册里轮胎磨损属于自费项目吗？",
    "远程控车 App 推送太多了，怎么关掉非必要通知？",
    "预约明天到店做常规检查，下午有空档吗？",
    "上次保养换的空调滤芯是原厂件吧？发票帮我再发一份。",
    "续航显示和实际差几公里，正常吗？",
    "冬天座椅加热怎么设置默认开启？",
]

# 动力电池与热安全
BATTERY_CHATS = [
    "充电时闻到焦糊味，仪表也跳了电池相关告警，有点慌。",
    "刚停好车底好像发热异常，手机 App 提示热管理系统告警。",
    "高速开完电池温度一直偏高，降不下来，要不要立刻停车？",
    "充电枪插着就听到异响，屏幕提示动力电池异常。",
    "昨天快充后续航掉得特别快，还伴有刺鼻气味。",
]

# 充电与高压
CHARGE_CHATS = [
    "家用桩充到一半就停了，车机报高压系统故障。",
    "公共快充枪锁死拔不出来，仪表显示充电异常。",
    "插枪后完全没反应，App 也连不上充电状态。",
    "慢充时车辆突然断电重启，高压相关灯亮了。",
    "充电口周围发烫，担心高压安全问题。",
]

# 制动与转向
BRAKE_CHATS = [
    "刹车时有明显异响，踩下去行程变长了。",
    "低速转弯方向盘发沉，偶发助力警告。",
    "下坡刹车抖动得很厉害，ABS 灯闪过一下。",
    "紧急制动时感觉制动力不够，有点吓人。",
    "方向盘回正很慢，仪表提示转向系统需检查。",
]

# 行驶中动力异常
POWER_CHATS = [
    "车辆无法启动，仪表只有供电没有 Ready。",
    "行驶中突然掉动力，只能滑行靠边。",
    "加速时动力输出一顿一顿的，像被限功率。",
    "停车后再启动多次失败，报动力系统故障。",
    "爬坡时动力严重不足，续航也掉得很快。",
]

# 智能驾驶与驾驶辅助
ADAS_CHATS = [
    "高速领航老是误刹，吓得我赶紧接管。",
    "车道保持一直晃，辅助驾驶不可用提示反复出现。",
    "自适应巡航跟车距离忽近忽远，感觉不太稳。",
    "夜路辅助驾驶识别护栏当障碍，突然减速。",
    "自动泊车中途退出，报传感器异常。",
]

# 车机、座舱和远程控车
IVI_CHATS = [
    "车机黑屏重启好几次了，空调和导航都没法用。",
    "远程解锁失败，App 显示车辆离线。",
    "OTA 升级后蓝牙电话断断续续，语音助手也不响应。",
    "中控卡死，只能显示开机画面，影响驾驶信息查看。",
    "远程预热开了没反应，车内温度完全没变化。",
]

# 重复维修与问题未解决
REPEAT_CHATS = [
    "同样的异响已经进店第三次了，还是没修好。",
    "上次说换了件，开两天故障灯又亮了。",
    "反复报同一个故障码，希望升级处理别再推脱。",
    "问题描述了好几次，每次都说观察观察。",
    "返修后问题依旧，要求重新诊断并给明确结论。",
]

# 道路救援与人员安全
RESCUE_CHATS = [
    "高速抛锚了，车上还有老人，请尽快安排道路救援。",
    "车辆停在应急车道起不来，有点危险请支援。",
    "暴雨天漏电跳闸后车辆无法移动，需要拖车。",
    "撞护栏后安全气囊没弹，人没事但车动不了。",
    "隧道里没电了，求道路救援，注意安全。",
]

# 质保、零部件与服务争议
WARRANTY_CHATS = [
    "这个件明明在质保期内，为什么要我自费？",
    "换上的零部件不像原厂，请提供溯源信息。",
    "服务顾问说法和质保条款不一致，我要申诉。",
    "同样故障别的车主免费处理，为什么我要收费？",
    "希望把质保争议升级到区域服务经理。",
]

# 边界 / 证据不足
GRAY_CHATS = [
    "车里偶尔有异味，说不清是不是焦糊，也没有告警。",
    "感觉刹车有点软，但仪表一切正常。",
    "充电偶尔中断一次，后来又正常了。",
    "辅助驾驶提示过一次传感器遮挡，清洁后好了。",
    "远程 App 延迟很高，不确定是车端还是网络问题。",
]

CHAT_MAP = {
    "safe": SAFE_CHATS,
    "battery": BATTERY_CHATS,
    "charge": CHARGE_CHATS,
    "brake": BRAKE_CHATS,
    "power": POWER_CHATS,
    "adas": ADAS_CHATS,
    "ivi": IVI_CHATS,
    "repeat": REPEAT_CHATS,
    "rescue": RESCUE_CHATS,
    "warranty": WARRANTY_CHATS,
    "gray": GRAY_CHATS,
}

TOPIC_MAP = {
    "safe": "无风险事件",
    "battery": "动力电池与热安全",
    "charge": "充电与高压系统异常",
    "brake": "制动与转向异常",
    "power": "行驶中动力异常",
    "adas": "智能驾驶与驾驶辅助反馈",
    "ivi": "车机、座舱和远程控车故障",
    "repeat": "重复维修与问题未解决",
    "rescue": "道路救援与人员安全",
    "warranty": "质保、零部件与服务争议",
    "gray": "无风险事件",
}

FAULT_TEMPLATES = {
    "battery": [
        {"code": "BMS_THERMAL_WARN", "description": "动力电池热管理告警，温度偏高。"},
        {"code": "CELL_IMBALANCE", "description": "电芯压差超限，伴随异味投诉。"},
    ],
    "charge": [
        {"code": "OBC_FAULT", "description": "车载充电机通信中断，充电中止。"},
        {"code": "HV_ISO_LOW", "description": "高压绝缘阻值偏低。"},
    ],
    "brake": [
        {"code": "ABS_INTERMITTENT", "description": "ABS 间歇性故障灯。"},
        {"code": "EPS_ASSIST_LOW", "description": "电动助力转向助力不足。"},
    ],
    "power": [
        {"code": "VCU_LIMIT_POWER", "description": "整车控制器触发限功率。"},
        {"code": "DRIVE_READY_FAIL", "description": "Ready 状态建立失败。"},
    ],
    "adas": [
        {"code": "FRONT_RADAR_BLOCK", "description": "前向毫米波雷达遮挡/异常。"},
        {"code": "ACC_UNAVAILABLE", "description": "自适应巡航功能不可用。"},
    ],
    "ivi": [
        {"code": "IVI_WATCHDOG_RESET", "description": "座舱域控制器看门狗复位。"},
        {"code": "TBOX_OFFLINE", "description": "车联网模块离线。"},
    ],
    "repeat": [
        {"code": "REPEAT_DTC_SAME", "description": "同一故障码 30 天内重复出现。"},
    ],
    "rescue": [
        {"code": "IMMOBILE_ROADSIDE", "description": "车辆无法行驶，需道路救援。"},
    ],
    "warranty": [
        {"code": "PARTS_DISPUTE", "description": "质保范围与费用归属存在争议。"},
    ],
}

SIGNAL_TEMPLATES = {
    "battery": {
        "alerts": ["battery_thermal_warning", "odor_report"],
        "battery_temp_c": (45, 62),
        "soc_pct": (20, 80),
    },
    "charge": {
        "alerts": ["charging_interrupt", "hv_system_fault"],
        "charge_power_kw": (0, 7),
        "soc_pct": (10, 90),
    },
    "brake": {
        "alerts": ["brake_performance_warn"],
        "abs_events": (1, 4),
    },
    "power": {
        "alerts": ["power_derate", "drive_ready_fail"],
        "motor_torque_limit": True,
    },
    "adas": {
        "alerts": ["adas_unavailable", "sudden_brake_event"],
        "takeover_requests": (1, 5),
    },
    "ivi": {
        "alerts": ["ivi_reboot", "tbox_offline"],
        "reboot_count_24h": (2, 8),
    },
    "repeat": {
        "alerts": ["repeat_visit"],
        "same_issue_count": (2, 5),
    },
    "rescue": {
        "alerts": ["vehicle_immobile", "roadside_assist_needed"],
        "location": "highway_shoulder",
    },
    "warranty": {
        "alerts": ["warranty_dispute"],
    },
    "safe": {
        "alerts": [],
        "soc_pct": (40, 90),
    },
    "gray": {
        "alerts": [],
        "note": "信号未见明确异常",
    },
}

VEHICLE_MODELS = [
    "AutoCare EV-Pro",
    "AutoCare SUV-AWD",
    "AutoCare Sedan-RWD",
    "AutoCare MPV-L",
]
CHANNELS = ["app", "hotline", "dealer", "roadside"]
REGIONS = ["广东", "浙江", "北京", "上海", "四川", "江苏", "湖北", "山东"]


def _time_factor() -> float:
    """基于当前小时返回请求频率因子，模拟售后进线曲线。"""
    hour = datetime.now().hour
    base = 0.5 + 0.5 * math.sin((hour - 6) / 24 * 2 * math.pi)
    if 19 <= hour <= 22:
        base *= 1.6
    elif 0 <= hour <= 5:
        base *= 0.35
    return max(base, 0.2)


class EventSimulator:
    """突发事件模拟器：热安全集中告警 / 充电异常批量上报 / 道路救援高峰。"""

    def __init__(self):
        self.active_event: str | None = None
        self.event_remaining: int = 0
        self.event_cooldown: int = 0

    def tick(self) -> str | None:
        if self.event_remaining > 0:
            self.event_remaining -= 1
            if self.event_remaining == 0:
                event = self.active_event
                self.active_event = None
                self.event_cooldown = random.randint(30, 80)
                return event
            return self.active_event

        if self.event_cooldown > 0:
            self.event_cooldown -= 1
            return None

        if random.random() < 0.02:
            self.active_event = random.choice(
                ["thermal_wave", "charge_batch", "rescue_peak"]
            )
            self.event_remaining = random.randint(8, 20)
            return self.active_event
        return None


def _build_vehicle_context() -> dict:
    mileage = random.randint(800, 120000)
    return {
        "vin_mask": f"LAC****{random.randint(1000, 9999)}",
        "model": random.choice(VEHICLE_MODELS),
        "model_year": random.randint(2022, 2026),
        "mileage_km": mileage,
        "region": random.choice(REGIONS),
        "software_version": f"OS-{random.randint(2, 5)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
    }


def _build_service_context(category: str) -> dict:
    urgency = {
        "battery": "high",
        "rescue": "critical",
        "charge": "high",
        "brake": "high",
        "power": "high",
        "repeat": "medium",
        "warranty": "medium",
        "adas": "medium",
        "ivi": "low",
        "safe": "low",
        "gray": "low",
    }.get(category, "low")
    return {
        "channel": random.choice(CHANNELS),
        "customer_id": f"C{random.randint(10000000, 99999999)}",
        "urgency": urgency,
        "hint_topic": TOPIC_MAP.get(category, "无风险事件"),
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _build_signal_summary(category: str) -> dict:
    tmpl = SIGNAL_TEMPLATES.get(category, SIGNAL_TEMPLATES["safe"])
    summary: dict = {"alerts": list(tmpl.get("alerts", []))}
    if "battery_temp_c" in tmpl:
        lo, hi = tmpl["battery_temp_c"]
        summary["battery_temp_c"] = round(random.uniform(lo, hi), 1)
    if "soc_pct" in tmpl:
        lo, hi = tmpl["soc_pct"]
        summary["soc_pct"] = random.randint(lo, hi)
    if "charge_power_kw" in tmpl:
        lo, hi = tmpl["charge_power_kw"]
        summary["charge_power_kw"] = round(random.uniform(lo, hi), 1)
    if "abs_events" in tmpl:
        lo, hi = tmpl["abs_events"]
        summary["abs_events"] = random.randint(lo, hi)
    if tmpl.get("motor_torque_limit"):
        summary["motor_torque_limit"] = True
    if "takeover_requests" in tmpl:
        lo, hi = tmpl["takeover_requests"]
        summary["takeover_requests"] = random.randint(lo, hi)
    if "reboot_count_24h" in tmpl:
        lo, hi = tmpl["reboot_count_24h"]
        summary["reboot_count_24h"] = random.randint(lo, hi)
    if "same_issue_count" in tmpl:
        lo, hi = tmpl["same_issue_count"]
        summary["same_issue_count"] = random.randint(lo, hi)
    if "location" in tmpl:
        summary["location"] = tmpl["location"]
    if "note" in tmpl:
        summary["note"] = tmpl["note"]
    return summary


def _build_fault_evidence(category: str) -> list[dict]:
    templates = FAULT_TEMPLATES.get(category, [])
    if not templates:
        return []
    picked = [random.choice(templates)]
    if len(templates) > 1 and random.random() < 0.25:
        other = random.choice([t for t in templates if t != picked[0]])
        picked.append(other)
    return [
        {
            "fault_code": t["code"],
            "description": t["description"],
            "occur_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for t in picked
    ]


def _build_service_history(category: str) -> dict:
    visits = 0
    if category == "repeat":
        visits = random.randint(2, 5)
    elif category in ("battery", "brake", "power", "charge"):
        visits = random.randint(0, 2)
    elif category == "warranty":
        visits = random.randint(1, 3)
    return {
        "open_work_orders": 1 if category not in ("safe", "gray") else 0,
        "recent_visit_count_30d": visits,
        "last_visit_summary": (
            "同主题问题多次进店未闭环。"
            if category == "repeat"
            else "近30日有相关检修记录。"
            if visits
            else "近30日无同类进店记录。"
        ),
        "warranty_status": random.choice(["in_warranty", "out_of_warranty", "partial"]),
    }


def _multi_round_chat(primary: str, category: str) -> list[dict]:
    evidence = [
        {
            "occur_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "role": "customer",
            "original_content": primary,
            "risk_point": (
                "存在安全或服务风险线索。"
                if category not in ("safe", "gray")
                else "未见明显风险线索。"
            ),
        }
    ]
    if random.random() < 0.35 and category not in ("safe", "gray"):
        replies = {
            "battery": ["请立即停车并远离车辆，我们协助安排救援。", "是否伴有冒烟或刺鼻气味？"],
            "charge": ["请勿继续充电，保留现场照片。", "充电桩品牌和故障码方便提供吗？"],
            "brake": ["请降低车速并尽快到安全区域。", "异响是在踩刹车时还是松开时？"],
            "power": ["是否还能亮 Ready？我们帮您派拖车。", "故障灯具体文案方便拍照发来吗？"],
            "adas": ["请先关闭辅助驾驶，改用人工驾驶。", "误刹发生时车速大概多少？"],
            "ivi": ["可以尝试长按电源重启车机。", "远程功能是否全部失败？"],
            "repeat": ["已为您标记重复未解决问题，升级服务跟进。", "前两次处理单号还在吗？"],
            "rescue": ["已创建道路救援工单，请保持电话畅通。", "车上有几位乘客？是否有人受伤？"],
            "warranty": ["我们会核对质保条款并回电。", "费用争议先暂停结算，转服务经理。"],
        }
        if category in replies:
            evidence.append(
                {
                    "occur_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "role": "agent",
                    "original_content": random.choice(replies[category]),
                    "risk_point": "坐席已进入处置引导。",
                }
            )
    return evidence


def generate_case(event: str | None = None) -> dict:
    """根据概率分布和当前事件生成一条模拟售后服务事件。"""
    if event == "thermal_wave":
        category = "battery" if random.random() < 0.7 else "safe"
    elif event == "charge_batch":
        category = "charge" if random.random() < 0.65 else "safe"
    elif event == "rescue_peak":
        category = "rescue" if random.random() < 0.55 else "power"
    else:
        category = random.choices(
            [
                "safe",
                "gray",
                "battery",
                "charge",
                "brake",
                "power",
                "adas",
                "ivi",
                "repeat",
                "rescue",
                "warranty",
            ],
            weights=[48, 6, 8, 7, 6, 6, 5, 5, 4, 3, 2],
        )[0]

    chat = random.choice(CHAT_MAP[category])
    service_context = _build_service_context(category)
    vehicle_context = _build_vehicle_context()
    conversation_evidence = _multi_round_chat(chat, category)
    vehicle_signal_summary = _build_signal_summary(category)
    fault_evidence = _build_fault_evidence(category)
    service_history_summary = _build_service_history(category)

    case_id = f"autocare-svc-{time.strftime('%Y%m%d-%H%M%S')}-{random.randint(1000, 9999)}"

    payload = {
        "case_id": case_id,
        "service_context": service_context,
        "vehicle_context": vehicle_context,
        "conversation_evidence": conversation_evidence,
        "vehicle_signal_summary": vehicle_signal_summary,
        "fault_evidence": fault_evidence,
        "service_history_summary": service_history_summary,
        # legacy 兼容字段
        "ticket_id": case_id,
        "audit_scene": service_context,
        "chat_evidence_list": conversation_evidence,
        "behavior_abnormal_list": fault_evidence,
    }
    return payload


def run_simulator(host: str = "127.0.0.1", port: int = 8000, interval: float = 1.0, concurrency: int = 5):
    """持续向研判服务发送模拟请求，异步并发。"""
    asyncio.run(_async_run(host, port, interval, concurrency))


async def _async_run(host: str, port: int, interval: float, concurrency: int):
    import httpx as _httpx

    url = f"http://{host}:{port}/judge"
    event_sim = EventSimulator()
    counter = {"n": 0}

    print("╔══════════════════════════════════════════╗")
    print("║  AutoCare 售后事件模拟器 v3.0 (async)    ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Guard-ML: {url:<29} ║")
    print(f"║  并发数: {concurrency}  基础间隔: {interval:.1f}s              ║")
    print("╚══════════════════════════════════════════╝")
    print("按 Ctrl+C 停止\n" + "-" * 60)

    sem = asyncio.Semaphore(concurrency)

    async def send_one(case: dict, event: str | None):
        async with sem:
            try:
                async with _httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=case)
                    resp.raise_for_status()
                    result = resp.json()

                counter["n"] += 1
                risk = result.get("risk_level", "?")
                topic = result.get("event_topic") or result.get("topic", "?")
                action = (
                    result.get("recommended_action")
                    or result.get("handling_suggestion", "?")
                )
                route = result.get("route", "?")
                risk_icon = {"high_risk": "🔴", "mid_risk": "🟡", "low_risk": "🟢"}.get(risk, "⚪")
                event_tag = f" ⚡{event}" if event else ""
                print(
                    f"[{counter['n']:04d}] {risk_icon} {case.get('case_id', '')[-15:]} │ "
                    f"{risk:<10} {str(topic)[:12]:<12} {str(action):<18} {route}{event_tag}"
                )
            except Exception as e:
                print(f"[错误] {e}")

    tasks = set()
    try:
        while True:
            event = event_sim.tick()
            case = generate_case(event)
            task = asyncio.create_task(send_one(case, event))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

            factor = _time_factor()
            jitter = random.uniform(-0.2, 0.2)
            actual_interval = max(0.1, (interval / factor) + jitter)
            await asyncio.sleep(actual_interval)
    except KeyboardInterrupt:
        pass

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    print(f"\n{'='*60}\n模拟器停止 | 共发送 {counter['n']} 条请求\n{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="AutoCare 售后事件模拟器 v3.0")
    parser.add_argument("--host", default="127.0.0.1", help="服务地址")
    parser.add_argument("--port", type=int, default=8000, help="服务端口")
    parser.add_argument("--interval", type=float, default=0.3, help="基础间隔(秒)")
    parser.add_argument("--concurrency", type=int, default=10, help="并发请求数")
    args = parser.parse_args()
    run_simulator(args.host, args.port, args.interval, args.concurrency)


if __name__ == "__main__":
    main()
