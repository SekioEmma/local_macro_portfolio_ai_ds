from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field


class SanitizedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    blocked: bool
    findings: list[str] = Field(default_factory=list)


_COMMON_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华"
    "金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花"
    "方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅"
    "皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明"
    "臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路"
    "娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝"
    "管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇"
    "邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌"
    "焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎"
    "祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸籍"
    "赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦"
    "雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连"
    "茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广"
    "禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空"
    "曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)

_FINDING_PATTERNS = (
    (
        "amount",
        (
            re.compile(r"[$¥￥]"),
            re.compile(r"(?i)\b(?:USD|RMB)\b"),
            re.compile(r"人民币"),
            re.compile(
                r"(?i)(?:USD|RMB|美元|人民币|[$¥￥])\s*"
                r"\d[\d,]*(?:\.\d+)?"
            ),
            re.compile(
                r"\d[\d,]*(?:\.\d+)?\s*"
                r"(?:美元|人民币|元|万元|亿元)"
            ),
        ),
    ),
    (
        "ticker_weight",
        (
            re.compile(
                r"(?i)\b[A-Z]{1,6}\s*:\s*"
                r"(?:\d+(?:\.\d+)?\s*%|0?\.\d+)(?![A-Za-z0-9_.])"
            ),
        ),
    ),
    (
        "account_number",
        (
            re.compile(
                r"(?i)(?:账号|账户|银行卡|卡号|account|bank\s*card|"
                r"card\s*(?:number|no\.?))"
                r"\s*(?:号|号码|number|no\.?)?\s*[:：#-]?\s*"
                r"(?:\d[\s-]?){6,}"
            ),
        ),
    ),
    (
        "local_path",
        (
            re.compile(r"(?i)\b[A-Z]:[\\/]"),
            re.compile(r"(?i)(?:^|\s)/(?:Users|home)(?:/|$)"),
            re.compile(r"(?i)(?:^|\s)/mnt/data(?:/|$)"),
        ),
    ),
    (
        "long_token",
        (
            re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_-])"),
        ),
    ),
    (
        "person_name",
        (
            re.compile(
                rf"(?:姓名|联系人|我叫)\s*[:：是为]?\s*"
                rf"[{_COMMON_SURNAMES}][\u4e00-\u9fff]{{1,2}}"
            ),
            re.compile(
                r"(?i)\b(?:name|contact)\s*(?:is|:|=)\s*"
                r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b"
            ),
        ),
    ),
)


def sanitize_query(text: str) -> SanitizedQuery:
    findings: list[str] = []
    if not text.strip():
        findings.append("empty_query")
    for finding, patterns in _FINDING_PATTERNS:
        if any(pattern.search(text) for pattern in patterns):
            findings.append(finding)
    if findings:
        return SanitizedQuery(text="", blocked=True, findings=findings)
    return SanitizedQuery(text=text, blocked=False, findings=[])


__all__ = [
    "SanitizedQuery",
    "sanitize_query",
]
