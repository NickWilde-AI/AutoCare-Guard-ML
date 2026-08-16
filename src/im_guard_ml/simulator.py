"""数据模拟器：模拟 IM 后端持续发送审核请求到 /judge 接口。

启动方式:
    python -m im_guard_ml.simulator --interval 1 --port 8000

模拟逻辑:
    - 时间感知：凌晨低谷(0.3x)、午间平稳(1x)、晚高峰(2-3x)
    - 突发事件：随机触发"代刷团伙集中作案"或"引流批量投放"
    - 话术多样：每条消息带随机变体（错别字、谐音、缩写）
    - 用户画像：注册天数、历史违规次数、设备类型等
    - 多轮对话：部分案例包含 2-4 条聊天记录
"""
from __future__ import annotations

import argparse
import asyncio
import math
import random
import time
from datetime import datetime

import httpx

# ===== 话术模板库 =====

# 安全对话（50+ 条，覆盖日常社交各场景）
SAFE_CHATS = [
    # 日常问候
    "你最近在忙什么呀？周末有空一起开黑吗？",
    "今天心情怎么样？看你动态说加班了",
    "早啊，昨晚睡得好吗",
    "好久没聊了，最近还好吗",
    "在吗？想问你个事",
    # 直播相关
    "今天直播唱的那首歌好好听，叫什么名字？",
    "明天几点开播呀？我准时来看",
    "你声音好好听，能唱首周杰伦的歌吗",
    "刚下班好累，来看你直播放松一下",
    "你直播间的氛围真好，大家都很友善",
    "昨天那个连麦的人好搞笑哈哈",
    "你今天穿的衣服好好看",
    "能不能唱一下那个《晴天》",
    "你开播我每次都来，加个粉丝团呗",
    # 游戏互动
    "你推荐的那个游戏我下了，确实好玩",
    "一起打排位吗？我段位掉了好多",
    "你那个皮肤怎么获得的？好帅",
    "今晚有空吗，组队打团",
    "你操作好厉害，带带我呗",
    # 生活闲聊
    "生日快乐！送你个小礼物",
    "最近天气好热，注意防暑啊",
    "你的猫好可爱，是什么品种？",
    "哈哈哈你说话太搞笑了，笑死我了",
    "推荐个好吃的外卖呗",
    "你那边下雨了吗？我这边暴雨",
    "周末要不要一起看电影",
    "你健身多久了？效果好明显",
    "最近在追什么剧？推荐一下",
    "你头像好好看，在哪拍的",
    # 粉丝互动
    "关注你好久了，终于鼓起勇气私聊",
    "你上次推荐的书我看完了，很好看",
    "今天的直播内容太有意思了",
    "能加个粉丝群吗？想认识其他粉丝",
    "你的声音好治愈，每天听着睡觉",
    "支持你！继续加油",
    "什么时候出新内容呀，期待",
    "你和上次那个连麦好有默契",
]

# 代刷/包榜（含变体、谐音、缩写）
BRUSH_CHATS = [
    "帮我代刷一下今晚的周榜，包榜到第一。",
    "老规矩，这次冲月榜前三，价格私聊。",
    "上次帮你刷的那个主播，这次还要继续吗？",
    "包榜费用怎么算？我要冲日榜第一。",
    "帮我把这个主播顶上去，预算两万。",
    "dai刷一下今晚的榜，保第一，价格好说",
    "冲bang费用多少？我要日ban前三",
    "兄弟，帮忙冲一下周榜，全包，钱不是问题",
    "上次那个事还能搞吗？这次目标月榜",
    "我出钱你出号，把她顶上去，三七分",
    "有没有资源帮我包一下今晚的榜单？要稳的",
    "找你帮忙刷一下，上次效果很好，继续合作",
    "能不能安排几个号帮我冲？预算五万以内",
    "这次搞大的，包周榜前三，多少钱你说",
    "帮我顶一下对面那个主播，让她掉出前五",
]

# 诈骗引流（含变体、谐音）
FRAUD_CHATS = [
    "加我私V，发你一个稳赚的项目，本金500起。",
    "加微信 xxx888，带你日入过千，零风险。",
    "私聊我，有个好项目介绍给你，保本保息。",
    "想赚钱吗？加我外部联系方式，带你上车。",
    "我这边有个投资渠道，回报率很高，感兴趣私我。",
    "加V: money666，每天稳定收入，不用你操心",
    "有个兼zhi的活，日结200-500，想做吗",
    "我朋友在做一个pj，收益很可观，了解一下？",
    "扫码加我，带你了解一个稳赚不赔的路子",
    "最近发现一个漏dong，稳定出jin，私我详聊",
    "你听说过XX平台吗？我在上面赚了不少，带你",
    "加我v信详聊，有个躺赚的事情跟你说",
    "兄弟想不想搞点外快？无风险那种",
    "我有个渠道可以低价充值，需要的私我",
    "帮你开通一个VIP渠道，半价，感兴趣吗",
]

# 私下交易
TRADE_CHATS = [
    "私下转账给我吧，平台抽成太高了。",
    "加我微信转账，给你打八折。",
    "别在平台充了，直接转我支付宝，便宜很多。",
    "我给你个收款码，走外部比较划算。",
    "走平台太贵了，你直接转给我，我给你发货",
    "咱们私下交易吧，省下手续费对半分",
    "加我V转钱，平台扣的太狠了",
    "你在app里充值不划算，我这里有折扣渠道",
    "直接发红包给我就行，不用走平台了",
    "我给你个链接，从那边下单便宜一半",
]

# 赌博引流（每条含博彩/押注/走势特征词）
GAMBLE_CHATS = [
    "有个棋牌平台很赚钱，押注就能回血，要不要一起玩？",
    "我在那个BC平台押注，赢了不少，带你上车",
    "加群看走势图，跟着计划买，稳赢不亏",
    "兄弟玩不玩？昨天下注赢了三千多",
    "有个pg平台，充100送100，提现秒到",
    "来我群里看分析师的走势计划，命中率90%以上",
    "那个博彩平台还在搞活动，押一波时时彩？",
    "有个jc群，每天跟单就行，上周回血一万",
    "六合彩有内部号，跟我下注稳赚",
    "输了别慌，加我带你回血翻本",
]

# 辱骂攻击
ABUSE_CHATS = [
    "你是不是傻逼？这都不懂",
    "滚吧你这个废物，别来我直播间了",
    "脑残吧你，说话都说不清楚",
    "你长得也太丑了吧，怪不得没人看",
    "垃圾主播，浪费我时间，去死吧",
    "贱人就是矫情，恶心死了",
    "智障玩意儿，赶紧滚蛋",
]

# 色情引流（每条均含可识别色情特征词）
PORN_CHATS = [
    "想看pian吗？加我另一个号，私密的那种",
    "有兴趣看那种视频吗？全套资源都有",
    "想约pao吗？我同城，价格私聊",
    "想找人裸聊吗？加我推荐个平台",
    "有需要的私我，那种照片应有尽有",
    "福利视频要不要？加我发你预览",
    "涩涩的资源管够，懂的来",
    "一夜情有兴趣吗？就在你附近",
]

# 灰区 / 边界案例（看起来像违规但其实正常，或看起来正常但可能有风险）
GRAY_ZONE_CHATS = [
    "我在淘宝开了个店，有空来逛逛",  # 可能引流但也可能是正常分享
    "上次说的那个事，咱们见面再聊",  # 含糊
    "你那个号还在用吗？能不能借我一下",  # 账号借用
    "我朋友想找人帮忙运营账号，有兴趣吗",
    "帮我点个赞呗，互帮互助",
    "你那个优惠券还有吗？能不能分享一下",
    "这个链接你看一下，是我做的小程序",
    "咱们换个地方聊吧，这里不方便",
]

# 辱骂攻击
ABUSE_CHATS = [
    "你是不是傻逼？这都不懂",
    "滚吧你这个废物，别来我直播间了",
    "脑残吧你，说话都说不清楚",
    "你长得也太丑了吧，怪不得没人看",
    "垃圾主播，浪费我时间",
]

# 政治敏感（模拟占位，每条含"政治敏感/敏感"特征词，不含真实敏感内容）
POLITICS_CHATS = [
    "你看了那个政治敏感的帖子了吗？帮我转发一下",
    "这个事情涉及政治敏感话题，我们私下传",
    "有个敏感事件的内幕，想不想看？别外传",
    "这种敏感话题别在直播间说，加我私聊",
    "帮忙扩散一下这条，内容比较敏感",
]

# 自伤诱导（每条含自伤/轻生特征词）
SELFHARM_CHATS = [
    "活着真没意思，不想活了",
    "你知道怎么自残吗？我想试试",
    "感觉这个世界不需要我了，想结束生命",
    "最近总有跳楼的念头，控制不住",
    "教教我割腕会不会很疼，我想解脱",
]

# 未成年保护（身份试探 + 诱导）
MINOR_CHATS = [
    "妹妹今年上几年级呀？看起来好小",
    "你是不是还在上学？看着像初中生",
    "你今年多大了？声音听着像高中生",
    "放学了吗？姐姐给你买礼物好不好",
    "你才14岁呀，那加个微信偷偷聊别让家长知道",
    "用你的压岁钱给我刷个礼物呗，回头加倍还你",
    "穿校服的样子真好看，能单独发我看看吗",
    "小朋友别告诉爸妈，咱俩的小秘密",
]

# 版权侵犯（盗版/破解/账号共享）
COPYRIGHT_CHATS = [
    "这部剧我有盗版资源，免费看，要的私我",
    "破解版软件需要吗？所有付费功能都解锁",
    "原价办会员太贵了，拼车会员了解一下，五个人一个号",
    "我这有全套付费课程的搬运，白菜价出",
    "网盘资源共享群，最新电影院线片都有",
    "账号共享车队招人，平摊会员费",
    "需要破解软件的加我，各种付费工具都有",
    "这个直播间的录播我翻录了，要的发你",
]

# 虚假信息（虚假中奖/冒充官方/谣言）
FAKEINFO_CHATS = [
    "恭喜你中奖了！点击链接领取iPhone，名额有限",
    "我是平台官方客服，你的账号异常需要验证",
    "官方通知：充值活动充100返500，仅限今天",
    "你听说了吗？那个主播其实是骗子，赶紧扩散",
    "内部消息，明天平台要大改规则，先囤点钻",
    "冒充不了别人，我就是官方的，加我领补偿",
    "扫码领取你的专属奖励，错过没有了",
]

# 违禁品交易（毒品/管制器具/黑灰产，模拟占位）
CONTRABAND_CHATS = [
    "需要那个吗？麻古、冰糖都有，懂的私聊",
    "仿真枪、管制刀具出货，要的加我",
    "听话水、迷药了解一下，效果好",
    "黑灰产工具、卡料批发，走加密渠道",
    "有非法教程，教你怎么搞钱，违禁那种",
    "实弹和弹药能搞到，价格私聊别问太多",
]

# ===== 行为异常模板库 =====
ABNORMAL_TEMPLATES = {
    "brush": [
        {"abnormal_type": "代刷/包榜行为", "abnormal_description": "30分钟内对目标主播突发性大额打赏{amount}元。"},
        {"abnormal_type": "代刷/包榜行为", "abnormal_description": "连续{days}天对同一主播固定时段打赏，疑似合同式包榜。"},
        {"abnormal_type": "异常打赏模式", "abnormal_description": "打赏间隔极短(平均{sec}秒/笔)，疑似脚本操作。"},
    ],
    "fraud": [
        {"abnormal_type": "批量投放", "abnormal_description": "10分钟内向{count}个不同主播账号私聊同一话术。"},
        {"abnormal_type": "批量投放", "abnormal_description": "24小时内向{count}个新用户发送相似消息，疑似批量引流。"},
        {"abnormal_type": "外部链接分发", "abnormal_description": "消息中包含外部链接/二维码，已向{count}人发送。"},
    ],
    "trade": [
        {"abnormal_type": "私下交易引导", "abnormal_description": "引导用户跳转外部支付渠道，涉及金额约{amount}元。"},
        {"abnormal_type": "绕过平台支付", "abnormal_description": "多次提及外部转账方式，历史{count}次类似行为。"},
    ],
    "gamble": [
        {"abnormal_type": "赌博引流", "abnormal_description": "发送疑似赌博平台链接，近7天向{count}人投递。"},
        {"abnormal_type": "赌博引流", "abnormal_description": "消息中包含赌博相关关键词(走势/押注/下注)，触发{count}次。"},
    ],
    "porn": [
        {"abnormal_type": "色情引流", "abnormal_description": "发送疑似色情内容引导，涉及外部平台跳转。"},
        {"abnormal_type": "色情引流", "abnormal_description": "私聊中发送疑似不雅图片/视频链接，已向{count}人发送。"},
    ],
    "minor": [
        {"abnormal_type": "未成年身份风险", "abnormal_description": "对方账号实名年龄显示未满18岁，存在身份试探话术。"},
        {"abnormal_type": "诱导私聊", "abnormal_description": "诱导疑似未成年用户转外部联系方式，近期{count}次类似行为。"},
    ],
    "copyright": [
        {"abnormal_type": "盗版资源分发", "abnormal_description": "消息含网盘/外链，疑似盗版资源，已向{count}人发送。"},
        {"abnormal_type": "账号共享售卖", "abnormal_description": "近7天{count}次提及拼车会员/账号共享，疑似侵权牟利。"},
    ],
    "fakeinfo": [
        {"abnormal_type": "虚假信息群发", "abnormal_description": "向{count}个用户群发含中奖/领取链接的相似消息。"},
        {"abnormal_type": "冒充官方", "abnormal_description": "昵称或话术冒充平台官方客服，诱导验证/充值。"},
    ],
    "contraband": [
        {"abnormal_type": "违禁品交易", "abnormal_description": "消息含违禁品关键词与外部加密联系方式，疑似交易引流。"},
        {"abnormal_type": "违禁品交易", "abnormal_description": "近期向{count}人投递违禁品售卖话术，走外部渠道结算。"},
    ],
}

# ===== 用户画像模板 =====
DEVICE_TYPES = ["iOS 17.4", "Android 14", "iOS 16.2", "Android 13", "HarmonyOS 4"]
REGIONS = ["广东", "浙江", "北京", "上海", "四川", "江苏", "福建", "湖北", "河南", "山东"]


def _time_factor() -> float:
    """基于当前小时返回请求频率因子，模拟真实流量曲线。

    凌晨 2-6 点: 0.2-0.4x (低谷)
    上午 9-12 点: 0.8-1.0x (平稳)
    下午 14-17 点: 0.9-1.1x (平稳)
    晚上 19-23 点: 1.5-3.0x (高峰)
    """
    hour = datetime.now().hour
    # 用正弦曲线模拟一天内的流量变化，高峰在 21 点
    base = 0.5 + 0.5 * math.sin((hour - 6) / 24 * 2 * math.pi)
    # 晚高峰额外加成
    if 19 <= hour <= 23:
        base *= 1.8
    elif 0 <= hour <= 5:
        base *= 0.4
    return max(base, 0.2)


class EventSimulator:
    """突发事件模拟器。

    随机触发短时间内违规率飙升的事件，模拟：
    - 代刷团伙集中上线
    - 引流机器人批量投放
    - 新型话术爆发
    """

    def __init__(self):
        self.active_event: str | None = None
        self.event_remaining: int = 0
        self.event_cooldown: int = 0  # 冷却计数，避免事件太频繁

    def tick(self) -> str | None:
        """每次请求调用，返回当前活跃事件类型或 None。"""
        if self.event_remaining > 0:
            self.event_remaining -= 1
            if self.event_remaining == 0:
                event = self.active_event
                self.active_event = None
                self.event_cooldown = random.randint(30, 80)
                return event  # 最后一条还是事件
            return self.active_event

        if self.event_cooldown > 0:
            self.event_cooldown -= 1
            return None

        # 2% 概率触发突发事件
        if random.random() < 0.02:
            self.active_event = random.choice(["brush_raid", "fraud_wave", "porn_burst"])
            self.event_remaining = random.randint(8, 20)
            return self.active_event

        return None


def _build_user_profile() -> dict:
    """生成随机用户画像。"""
    reg_days = random.choices(
        [random.randint(0, 3), random.randint(4, 30), random.randint(31, 365), random.randint(366, 1500)],
        weights=[15, 25, 40, 20],
    )[0]
    return {
        "user_id": f"U{random.randint(100000000, 999999999)}",
        "register_days": reg_days,
        "history_violations": random.choices([0, 1, 2, random.randint(3, 8)], weights=[70, 15, 10, 5])[0],
        "device_type": random.choice(DEVICE_TYPES),
        "region": random.choice(REGIONS),
        "level": random.randint(1, 60),
    }


def _fill_abnormal(template: dict) -> dict:
    """填充异常模板中的占位符。"""
    desc = template["abnormal_description"]
    desc = desc.replace("{amount}", str(random.choice([3000, 5000, 8000, 10000, 15000, 20000, 30000])))
    desc = desc.replace("{count}", str(random.randint(4, 30)))
    desc = desc.replace("{days}", str(random.randint(3, 14)))
    desc = desc.replace("{sec}", str(random.randint(2, 8)))
    return {"abnormal_type": template["abnormal_type"], "abnormal_description": desc}


def _multi_round_chat(primary: str, category: str) -> list[dict]:
    """生成多轮对话证据（1-3 条）。"""
    evidence = [
        {
            "occur_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "original_content": primary,
            "risk_point": "存在违规关键词。" if category != "safe" else "无明显风险词。",
        }
    ]
    # 30% 概率有第二条回复
    if random.random() < 0.3 and category != "safe":
        replies = {
            "brush": ["好的，老价格，包你满意。", "没问题，今晚给你安排。", "行，这次冲前三保底。"],
            "fraud": ["好的加了，什么项目？", "真的假的？靠谱吗", "行，我看看怎么回事"],
            "trade": ["好，那你发收款码吧", "行，支付宝还是微信？", "了解，那走外部吧"],
            "gamble": ["听起来不错，怎么玩？", "赢了怎么提现？", "行，你拉我进群看走势"],
            "porn": ["什么资源？", "私密的？多少钱", "加了，发我看看"],
            "minor": ["我才上初二啦", "你别告诉我妈妈哦", "好呀，加你微信"],
            "copyright": ["怎么拼车？多少钱", "盗版清晰吗", "发我网盘链接"],
            "fakeinfo": ["真的中奖了？怎么领", "你是官方客服吗", "链接安全吗"],
            "contraband": ["怎么交易？", "走什么渠道", "价格多少，靠谱吗"],
        }
        if category in replies:
            reply = random.choice(replies[category])
            evidence.append({
                "occur_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "original_content": reply,
                "risk_point": "回复确认违规意图。" if category != "safe" else "",
            })
    return evidence


def generate_case(event: str | None = None) -> dict:
    """根据概率分布和当前事件生成一条模拟审核工单。"""

    # 事件期间强制覆盖分布
    if event == "brush_raid":
        category = "brush" if random.random() < 0.7 else "safe"
    elif event == "fraud_wave":
        category = "fraud" if random.random() < 0.6 else "safe"
    elif event == "porn_burst":
        category = "porn" if random.random() < 0.5 else "safe"
    else:
        # 正常分布：真实生产环境绝大多数为正常对话，违规为长尾。
        # 各违规类按平台真实治理强度排序（代刷/诈骗/赌博为高发，违禁/自伤极低频）。
        category = random.choices(
            [
                "safe", "gray", "brush", "fraud", "gamble", "trade",
                "porn", "abuse", "fakeinfo", "copyright", "politics",
                "minor", "selfharm", "contraband",
            ],
            weights=[
                62, 6, 6, 5, 4, 3.5,
                3, 3, 2, 2, 1.2,
                1, 0.6, 0.6,
            ],
        )[0]

    # 选择话术
    chat_map = {
        "safe": SAFE_CHATS,
        "brush": BRUSH_CHATS,
        "fraud": FRAUD_CHATS,
        "gamble": GAMBLE_CHATS,
        "trade": TRADE_CHATS,
        "porn": PORN_CHATS,
        "abuse": ABUSE_CHATS,
        "politics": POLITICS_CHATS,
        "selfharm": SELFHARM_CHATS,
        "minor": MINOR_CHATS,
        "copyright": COPYRIGHT_CHATS,
        "fakeinfo": FAKEINFO_CHATS,
        "contraband": CONTRABAND_CHATS,
        "gray": GRAY_ZONE_CHATS,
    }
    chat = random.choice(chat_map[category])

    # 用户画像
    profile = _build_user_profile()
    # 违规用户画像偏向：新号、有历史违规
    if category not in ("safe", "gray"):
        if random.random() < 0.4:
            profile["register_days"] = random.randint(0, 7)
        if random.random() < 0.3:
            profile["history_violations"] = random.randint(1, 5)

    # 礼物金额
    if category == "brush":
        gift_value = random.choices(
            [random.randint(5000, 10000), random.randint(10000, 30000), random.randint(30000, 80000)],
            weights=[40, 40, 20],
        )[0]
    elif category == "trade":
        gift_value = random.randint(500, 5000)
    elif category == "safe":
        gift_value = random.choices(
            [0, random.randint(1, 100), random.randint(100, 500), random.randint(500, 2000)],
            weights=[40, 30, 20, 10],
        )[0]
    else:
        gift_value = random.randint(0, 200)

    # 亲密度
    intimacy_map = {
        "safe": random.choice(["高", "中", "低", "中", "高"]),
        "brush": random.choice(["无", "低", "无"]),
        "fraud": "无",
        "trade": random.choice(["中", "低"]),
        "gamble": "无",
        "porn": "无",
        "abuse": random.choice(["无", "低"]),
        "politics": random.choice(["低", "中"]),
        "selfharm": random.choice(["中", "高"]),
        "minor": random.choice(["无", "低"]),
        "copyright": random.choice(["低", "无"]),
        "fakeinfo": "无",
        "contraband": "无",
        "gray": random.choice(["中", "低", "无"]),
    }
    intimacy = intimacy_map[category]

    # 登录行为：引流/黑产类多为异地批量号
    login = (
        "异地登录。"
        if category in ("fraud", "gamble", "porn", "fakeinfo", "contraband", "copyright")
        or (category == "brush" and random.random() < 0.6)
        else "本机登录。"
    )

    # 行为异常
    abnormals = []
    if category in ABNORMAL_TEMPLATES:
        tmpl = random.choice(ABNORMAL_TEMPLATES[category])
        abnormals = [_fill_abnormal(tmpl)]
        # 20% 概率有第二条异常
        if random.random() < 0.2 and len(ABNORMAL_TEMPLATES[category]) > 1:
            tmpl2 = random.choice([t for t in ABNORMAL_TEMPLATES[category] if t != tmpl])
            abnormals.append(_fill_abnormal(tmpl2))

    # 聊天证据（多轮）
    evidence = _multi_round_chat(chat, category)

    ticket_id = f"im-audit-{time.strftime('%Y%m%d-%H%M%S')}-{random.randint(1000, 9999)}"

    return {
        "ticket_id": ticket_id,
        "audit_scene": {
            "chat_type": "IM私聊",
            "user_intimacy": intimacy,
            "user_profile": profile,
            "behavior_key_summary": {
                "login_behavior": login,
                "search_behavior": "搜索UID。" if category in ("fraud", "brush") else "无搜索行为。",
                "follow_behavior": random.choice(["互关。", "单向关注。", "无关注。"]),
                "enter_room_behavior": random.choice(["近30日频繁进房。", "偶尔进房。", "首次进房。", "短时间内连续进入多个房间。"]),
                "mic_interact_behavior": random.choice(["无互动。", "偶尔连麦。", "频繁连麦。"]),
                "t_bean_consume": "极大额消费。" if gift_value > 10000 else "大额消费。" if gift_value > 5000 else "中等额度消费。" if gift_value > 500 else "少量消费。" if gift_value > 0 else "无消费。",
                "reward_behavior": "持续高频大额打赏，旨在推高榜单。" if gift_value > 10000 else "大额打赏。" if gift_value > 5000 else "礼物记录稳定，无突发尖峰。" if gift_value > 0 else "无礼物记录。",
                "gift_total_value": gift_value,
                "gift_total_count": max(1, gift_value // random.randint(500, 3000)) if gift_value > 0 else 0,
            },
        },
        "chat_evidence_list": evidence,
        "behavior_abnormal_list": abnormals,
    }


def run_simulator(host: str = "127.0.0.1", port: int = 8000, interval: float = 1.0, concurrency: int = 5):
    """持续向审核服务发送模拟请求，异步并发，适配 API 模式高延迟。"""
    asyncio.run(_async_run(host, port, interval, concurrency))


def _extract_behavior_features(case: dict) -> dict:
    """从模拟案例中提取行为特征供 RiskHub 规则引擎使用。"""
    summary = case.get("audit_scene", {}).get("behavior_key_summary", {})
    profile = case.get("audit_scene", {}).get("user_profile", {})
    abnormals = case.get("behavior_abnormal_list", [])

    features = {}
    # 消息频率
    gift_count = summary.get("gift_total_count", 0)
    if gift_count:
        features["recent_message_count"] = random.randint(50, 200)

    # 外联数（如果有批量投放异常，设较高值）
    if any("批量" in a.get("abnormal_description", "") or "投放" in a.get("abnormal_description", "") for a in abnormals):
        features["external_contact_count"] = random.randint(10, 30)
    elif profile.get("history_violations", 0) > 0:
        features["external_contact_count"] = random.randint(5, 15)

    return features


async def _async_run(host: str, port: int, interval: float, concurrency: int):
    import httpx as _httpx

    url = f"http://{host}:{port}/judge"
    # 同时向 RiskHub 发送请求，让两个看板都有数据
    riskhub_url = "http://127.0.0.1:8080/api/v1/audit/submit"
    riskhub_token = "Bearer tk_im_service_2024"
    event_sim = EventSimulator()
    counter = {"n": 0}

    print(f"╔══════════════════════════════════════════╗")
    print(f"║   IM Guard 数据模拟器 v3.0 (async)       ║")
    print(f"╠══════════════════════════════════════════╣")
    print(f"║  Guard-ML: {url:<29} ║")
    print(f"║  RiskHub:  {riskhub_url:<29} ║")
    print(f"║  并发数: {concurrency}  基础间隔: {interval:.1f}s              ║")
    print(f"╚══════════════════════════════════════════╝")
    print("按 Ctrl+C 停止\n" + "-" * 60)

    sem = asyncio.Semaphore(concurrency)

    async def send_one(case: dict, event: str | None):
        async with sem:
            try:
                async with _httpx.AsyncClient(timeout=30.0) as client:
                    # 发送到 Guard-ML (看板数据)
                    resp = await client.post(url, json=case)
                    resp.raise_for_status()
                    result = resp.json()

                    # 同时发送到 RiskHub (走完整审核链路)
                    riskhub_payload = {
                        "requestId": case.get("ticket_id", f"sim-{counter['n']}"),
                        "bizType": "im",
                        "scene": "private_chat",
                        "userId": case.get("audit_scene", {}).get("user_profile", {}).get("user_id", "unknown"),
                        "contentText": case.get("chat_evidence_list", [{}])[0].get("original_content", "") if case.get("chat_evidence_list") else "",
                        "chatEvidenceList": [e.get("original_content", "") for e in case.get("chat_evidence_list", [])],
                        "behaviorFeatures": _extract_behavior_features(case),
                        "mode": "sync",
                    }
                    try:
                        await client.post(
                            riskhub_url,
                            json=riskhub_payload,
                            headers={"Authorization": riskhub_token, "Content-Type": "application/json"},
                            timeout=5.0,
                        )
                    except Exception:
                        pass  # RiskHub 不可用时静默忽略，不影响 Guard-ML 模拟

                counter["n"] += 1
                risk = result.get("risk_level", "?")
                topic = result.get("topic", "?")
                action = result.get("handling_suggestion", "?")
                route = result.get("route", "?")
                risk_icon = {"high_risk": "🔴", "mid_risk": "🟡", "low_risk": "🟢"}.get(risk, "⚪")
                event_tag = f" ⚡{event}" if event else ""
                print(
                    f"[{counter['n']:04d}] {risk_icon} {case['ticket_id'][-15:]} │ "
                    f"{risk:<10} {topic:<12} {action:<14} {route}{event_tag}"
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
    parser = argparse.ArgumentParser(description="IM Guard 数据模拟器 v3.0")
    parser.add_argument("--host", default="127.0.0.1", help="服务地址")
    parser.add_argument("--port", type=int, default=8000, help="服务端口")
    parser.add_argument("--interval", type=float, default=0.3, help="基础间隔(秒)")
    parser.add_argument("--concurrency", type=int, default=10, help="并发请求数")
    args = parser.parse_args()
    run_simulator(args.host, args.port, args.interval, args.concurrency)


if __name__ == "__main__":
    main()
