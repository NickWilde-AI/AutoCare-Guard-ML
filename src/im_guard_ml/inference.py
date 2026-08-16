from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from .parsing import parse_judge_output
from .prompting import render_infer_text, render_user_prompt

logger = logging.getLogger(__name__)


@dataclass
class HeuristicJudge:
    """CPU-only fallback for demos when no fine-tuned checkpoint is present."""

    rubrics: dict[str, str]

    def predict(self, case: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            [str(case.get("audit_scene", ""))]
            + [str(x) for x in case.get("chat_evidence_list", [])]
            + [str(x) for x in case.get("behavior_abnormal_list", [])]
        ).lower()
        # 主题关键词检测（覆盖全部 11 种违规主题，中英文关键词）
        brush = any(k in text for k in [
            "代刷", "dai刷", "代chong", "包榜", "冲榜", "冲bang", "冲一下榜", "日ban", "周ban",
            "榜单", "周榜", "月榜", "日榜", "老规矩", "顶上去", "顶一下", "包一下", "包你", "全包",
            "出钱你出号", "三七分", "对半分", "冲前", "保第一", "保底",
        ])
        minor = any(k in text for k in [
            "未成年", "小学", "初中", "高中生", "小朋友", "几年级", "上几年级", "今年多大", "多大了",
            "13岁", "14岁", "15岁", "16岁", "未满18", "你是学生", "还在上学", "放学", "校服", "压岁钱",
            # English
            "underage", "minor", "child abuse", "child exploit", "pedophil", "groom",
            "young girl", "young boy", "lolita", "preteen",
        ])
        self_harm = any(k in text for k in [
            "自杀", "自残", "割腕", "跳楼", "活着没意思", "不想活", "不想活了", "结束生命",
            "离开这个世界", "世界不需要我", "想轻生", "怎么自残", "解脱",
            # English
            "suicide", "self-harm", "kill myself", "end my life", "cut myself", "want to die",
            "how to hang", "overdose", "slit my wrist", "jump off",
        ])
        contraband = any(k in text for k in [
            "违禁", "枪支", "枪zhi", "毒品", "管制刀具", "管制器具", "迷药", "迷魂药", "麻古",
            "弹药", "仿真枪", "催情", "听话水", "黑灰产", "卡料", "料子", "实弹",
            # English
            "illegal weapon", "firearm", "buy gun", "sell gun", "make a bomb", "explosive",
            "drug deal", "cocaine", "methamphetamine", "fentanyl", "heroin",
            "chemical weapon", "biological weapon", "ricin", "anthrax", "synthesize",
        ])
        porn = any(k in text for k in [
            "色情", "不雅", "看pian", "看片", "小jj", "约pao", "一夜情", "裸聊", "福利视频",
            "私密视频", "那种视频", "那种照片", "资源都有", "全套资源", "成人", "黄色", "涩涩",
            # English
            "porn", "nude", "nsfw", "sexual content", "explicit", "erotic",
            "sex video", "onlyfans", "escort", "prostitut",
        ])
        politics = any(k in text for k in [
            "政治", "政治敏感", "反动", "颠覆", "分裂", "邪教", "敏感话题", "敏感事件",
            "境外势力", "煽动", "游行", "示威", "敏感人物",
            # English
            "overthrow government", "insurrection", "terrorism", "terrorist attack",
            "extremist", "radicalize", "violent protest", "assassination",
        ])
        gamble = any(k in text for k in [
            "棋牌", "押注", "下注", "走势", "走势图", "跟单", "跟计划", "BC平台", "bc平台", "jc群",
            "pg平台", "博彩", "彩票", "时时彩", "六合", "提现", "充100送100", "稳赢", "命中率", "回血",
            # English
            "gambling", "casino", "bet online", "poker site", "slot machine",
        ])
        fraud = any(k in text for k in [
            "私V", "私v", "稳赚", "本金", "加微信", "加我", "加V", "加v", "v信", "vx", "威信",
            "日入", "日结", "兼zhi", "兼职", "漏dong", "漏洞", "躺赚", "外快", "投资渠道", "回报率",
            "保本保息", "上车", "稳定收入", "扫码加", "带你赚", "躺着赚", "项目介绍", "低价充值",
            # English
            "phishing", "scam", "ponzi", "pyramid scheme", "nigerian prince",
            "send me money", "wire transfer", "steal identity", "credit card fraud",
            "social engineering", "impersonat",
        ])
        trade = any(k in text for k in [
            "私下", "私下交易", "折扣", "打八折", "打折", "外部", "走外部", "收款", "收款码",
            "转账", "转我", "转支付宝", "发红包", "不走平台", "别在平台", "省手续费", "省下手续费",
            "平台抽成", "平台扣", "私下转", "走平台太贵",
        ])
        copyright_v = any(k in text for k in [
            "盗版", "破解版", "破解软件", "免费看", "免费资源", "翻录", "搬运", "盗播",
            "付费内容", "原价", "资源共享", "网盘资源", "账号共享", "车队", "拼车会员", "共享会员",
            # English
            "piracy", "pirated", "crack software", "torrent", "illegal download",
            "copyright infring", "dmca", "stolen content", "rip movie",
        ])
        fake_info = any(k in text for k in [
            "虚假", "谣言", "假新闻", "编造", "不实", "中奖", "恭喜你中", "官方通知", "冒充官方",
            "客服通知", "账号异常", "点击领取", "免费领", "扫码领奖", "内部消息",
            # English
            "fake news", "misinformation", "disinformation", "conspiracy", "hoax",
            "false claim", "fabricat", "deepfake", "manipulat",
        ])
        abuse = any(k in text for k in [
            "傻逼", "sb", "去死", "垃圾", "贱人", "废物", "脑残", "智障", "滚", "滚蛋", "你妈",
            "畜生", "恶心", "丑", "怪不得没人看", "不要脸",
            # English
            "hate speech", "racial slur", "nigger", "faggot", "kill you",
            "death threat", "i will hurt", "harass",
        ])

        high_behavior = any(k in text for k in ["极大额", "大额", "高频", "批量", "短时间", "突发性"])
        gift_value = _gift_total_value(case)

        # 主题优先级判定：强禁类目（一票否决）优先于泛化的引流/交易类，
        # 避免"加我看片"这类被诈骗/交易关键词抢先吞掉。
        topic = "无主题"
        if minor:
            topic = "未成年保护"
        elif self_harm:
            topic = "自伤诱导"
        elif contraband:
            topic = "违禁品交易"
        elif porn:
            topic = "色情诱导"
        elif politics:
            topic = "政治敏感"
        elif brush:
            topic = "代刷/包榜"
        elif gamble:
            topic = "赌博引流"
        elif fraud:
            topic = "诈骗引流"
        elif trade:
            topic = "私下交易"
        elif copyright_v:
            topic = "版权侵犯"
        elif fake_info:
            topic = "虚假信息"
        elif abuse:
            topic = "辱骂攻击"

        violation = any([brush, fraud, trade, gamble, porn, politics, abuse, minor, copyright_v, fake_info, self_harm, contraband])
        violation = violation or (high_behavior and gift_value >= 5000)

        # 严重程度判断：强禁类目直接高风险；引流/代刷类需行为或金额印证才升高。
        high = violation and (
            gift_value >= 5000
            or (fraud and high_behavior)
            or (brush and high_behavior)
            or (gamble and high_behavior)
            or porn
            or politics
            or self_harm
            or contraband
            or minor
        )
        mid = violation and not high

        if not violation:
            return {
                "risk_level": "low_risk",
                "topic": topic,
                "correlation_analysis": "聊天内容与行为证据未形成明确违规链条。",
                "final_judgment": "not_exist_violation",
                "judgment_basis": "未发现明确违规话术或可印证的异常行为。",
                "handling_suggestion": "ignore",
                "confidence": 0.85,
            }
        return {
            "risk_level": "high_risk" if high else "mid_risk",
            "topic": topic,
            "correlation_analysis": "聊天语义与行为异常存在同向印证，具备违规风险。",
            "final_judgment": "exist_violation",
            "judgment_basis": "命中违规语义要点，并存在行为侧或上下文证据支撑。",
            "handling_suggestion": "ban_account" if high else "limit_account" if mid else "warning",
            "confidence": 0.95 if high else 0.88,
        }


def _gift_total_value(case: dict[str, Any]) -> float:
    summary = case.get("audit_scene", {}).get("behavior_key_summary", {})
    try:
        return float(summary.get("gift_total_value", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


class TransformersJudge:
    def __init__(self, model_path: str, rubrics: dict[str, str], max_new_tokens: int = 384):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.rubrics = rubrics
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            trust_remote_code=True,
        ).eval()
        if torch.cuda.is_available():
            self.model = self.model.cuda()

    def predict(self, case: dict[str, Any]) -> dict[str, Any]:
        prompt = render_infer_text(case, self.rubrics)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with self.torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        gen = self.tokenizer.decode(output[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
        return parse_judge_output(gen)


class APIJudge:
    """Judge that calls an OpenAI-compatible API (e.g. DashScope Qwen) for inference.

    This allows running the full pipeline on a Mac without GPU by using a remote
    model API. Supports any OpenAI-compatible endpoint.

    Usage:
        judge = APIJudge(rubrics, model="qwen-plus")
        result = judge.predict(case)
    """

    def __init__(
        self,
        rubrics: dict[str, str],
        model: str = "qwen-plus",
        api_base: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 384,
        temperature: float = 0.0,
    ):
        self.rubrics = rubrics
        self.model = model
        self.api_base = api_base or os.environ.get(
            "QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.api_key = api_key or os.environ.get("QWEN_API_KEY", "")
        self.max_tokens = max_tokens
        self.temperature = temperature

    def predict(self, case: dict[str, Any]) -> dict[str, Any]:
        import httpx

        user_prompt = render_user_prompt(case, self.rubrics)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return parse_judge_output(content)
        except Exception as e:
            logger.error("API Judge failed: %s", e)
            return {
                "risk_level": "low_risk",
                "topic": "无主题",
                "correlation_analysis": f"API 调用失败: {e}",
                "final_judgment": "not_exist_violation",
                "judgment_basis": "API 异常，默认安全。",
                "handling_suggestion": "ignore",
            }

