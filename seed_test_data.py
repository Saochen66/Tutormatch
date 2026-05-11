import json

from app import app
from models import db, User, TutorInfo, StudentInfo

DEFAULT_PASSWORD = "test12345"

# Extracted and normalized from the provided tutoring-group messages.
STUDENT_SEED = [
    {
        "nickname": "生源_四英_01",
        "gender": "男",
        "subjects": "英语",
        "grade": "四年级",
        "teaching_mode": "线下",
        "budget_upper": 120,
        "requirements": "英语提分与兴趣培养，经验丰富优先",
        "wechat": "heb033002114",
        "teaching_time": {"周二": {"start": "15:00", "end": "17:00"}, "周六": {"start": "09:00", "end": "11:00"}},
    },
    {
        "nickname": "生源_初二数_02",
        "gender": "男",
        "subjects": "数学",
        "grade": "初二",
        "teaching_mode": "线下",
        "budget_upper": 120,
        "requirements": "引导学习态度，授课生动，需有经验",
        "wechat": "heb032962107",
        "teaching_time": {"周三": {"start": "19:00", "end": "20:30"}, "周五": {"start": "19:00", "end": "20:30"}},
    },
    {
        "nickname": "生源_高二数_03",
        "gender": "女",
        "subjects": "数学",
        "grade": "高二",
        "teaching_mode": "线下",
        "budget_upper": 200,
        "requirements": "希望提升解题能力，长期稳定",
        "wechat": "heb032762091",
        "teaching_time": {"周日": {"start": "09:00", "end": "11:00"}},
    },
    {
        "nickname": "生源_初一全科_04",
        "gender": "女",
        "subjects": "语文,数学,英语,物理,化学",
        "grade": "初一",
        "teaching_mode": "线下",
        "budget_upper": 140,
        "requirements": "陪写作业和答疑，周内晚间可长期",
        "wechat": "xueyuan0404",
        "teaching_time": {
            "周一": {"start": "19:30", "end": "21:30"},
            "周二": {"start": "19:30", "end": "21:30"},
            "周三": {"start": "19:30", "end": "21:30"},
            "周四": {"start": "19:30", "end": "21:30"},
            "周五": {"start": "19:30", "end": "21:30"},
        },
    },
    {
        "nickname": "生源_高二理_05",
        "gender": "男",
        "subjects": "数学,物理",
        "grade": "高二",
        "teaching_mode": "线下",
        "budget_upper": 120,
        "requirements": "理科强化，周末可灵活安排",
        "wechat": "xueyuan0505",
        "teaching_time": {"周五": {"start": "19:00", "end": "21:00"}, "周六": {"start": "14:00", "end": "16:00"}},
    },
    {
        "nickname": "生源_一年体_06",
        "gender": "男",
        "subjects": "体育",
        "grade": "一年级",
        "teaching_mode": "线下",
        "budget_upper": 60,
        "requirements": "篮球基础训练，耐心有方法",
        "wechat": "xueyuan0606",
        "teaching_time": {"周二": {"start": "18:30", "end": "19:30"}, "周四": {"start": "18:30", "end": "19:30"}, "周六": {"start": "18:30", "end": "19:30"}},
    },
    {
        "nickname": "生源_初二数英_07",
        "gender": "男",
        "subjects": "数学,英语",
        "grade": "初二",
        "teaching_mode": "线下",
        "budget_upper": 80,
        "requirements": "初中数英提分，最好有中考经验",
        "wechat": "xueyuan0707",
        "teaching_time": {"周六": {"start": "10:00", "end": "12:00"}},
    },
    {
        "nickname": "生源_六数网_08",
        "gender": "男",
        "subjects": "数学",
        "grade": "六年级",
        "teaching_mode": "线上",
        "budget_upper": 80,
        "requirements": "周末网课，基础巩固与计算提升",
        "wechat": "wangke033140",
        "teaching_time": {"周六": {"start": "19:00", "end": "20:30"}, "周日": {"start": "10:00", "end": "11:30"}},
    },
    {
        "nickname": "生源_高一化网_09",
        "gender": "男",
        "subjects": "化学",
        "grade": "高一",
        "teaching_mode": "线上",
        "budget_upper": 110,
        "requirements": "周末网课，知识点梳理和题型训练",
        "wechat": "wangke033101",
        "teaching_time": {"周六": {"start": "14:00", "end": "16:00"}},
    },
    {
        "nickname": "生源_高二物_10",
        "gender": "女",
        "subjects": "物理",
        "grade": "高二",
        "teaching_mode": "线下",
        "budget_upper": 140,
        "requirements": "周六固定上课，偏好长期带课",
        "wechat": "xueyuan1010",
        "teaching_time": {"周六": {"start": "16:00", "end": "18:00"}},
    },
]

# Created tutor records that intentionally overlap with the above demands.
TUTOR_SEED = [
    {
        "nickname": "家教_英语小学_A",
        "gender": "女",
        "subjects": "英语",
        "grades": "四年级,五年级,六年级",
        "teaching_mode": "线下,线上",
        "fee": 120,
        "introduction": "小学英语提分与兴趣培养，耐心负责",
        "wechat": "tutorA001",
        "teaching_time": {"周二": {"start": "14:00", "end": "18:00"}, "周六": {"start": "09:00", "end": "12:00"}},
    },
    {
        "nickname": "家教_初中数学_B",
        "gender": "男",
        "subjects": "数学",
        "grades": "初一,初二,初三",
        "teaching_mode": "线下",
        "fee": 120,
        "introduction": "擅长初中数学方法训练，课堂节奏好",
        "wechat": "tutorB002",
        "teaching_time": {"周三": {"start": "18:30", "end": "21:00"}, "周五": {"start": "18:30", "end": "21:00"}},
    },
    {
        "nickname": "家教_高中数学_C",
        "gender": "女",
        "subjects": "数学",
        "grades": "高一,高二,高三",
        "teaching_mode": "线下,线上",
        "fee": 200,
        "introduction": "高中数学体系化辅导，重视错题复盘",
        "wechat": "tutorC003",
        "teaching_time": {"周日": {"start": "08:30", "end": "12:00"}},
    },
    {
        "nickname": "家教_全科陪学_D",
        "gender": "女",
        "subjects": "语文,数学,英语,物理,化学",
        "grades": "初一,初二",
        "teaching_mode": "线下",
        "fee": 140,
        "introduction": "可做作业辅导与全科答疑，沟通细致",
        "wechat": "tutorD004",
        "teaching_time": {"周一": {"start": "19:00", "end": "21:30"}, "周二": {"start": "19:00", "end": "21:30"}, "周三": {"start": "19:00", "end": "21:30"}},
    },
    {
        "nickname": "家教_高二理综_E",
        "gender": "男",
        "subjects": "数学,物理",
        "grades": "高二,高三",
        "teaching_mode": "线下",
        "fee": 120,
        "introduction": "理科思维训练，擅长函数与力学模块",
        "wechat": "tutorE005",
        "teaching_time": {"周五": {"start": "19:00", "end": "21:00"}, "周六": {"start": "14:00", "end": "17:00"}},
    },
    {
        "nickname": "家教_少儿体育_F",
        "gender": "男",
        "subjects": "体育",
        "grades": "一年级,二年级,三年级",
        "teaching_mode": "线下",
        "fee": 60,
        "introduction": "少儿篮球基本功训练，注重兴趣和习惯",
        "wechat": "tutorF006",
        "teaching_time": {"周二": {"start": "18:00", "end": "20:00"}, "周四": {"start": "18:00", "end": "20:00"}},
    },
    {
        "nickname": "家教_初中数英_G",
        "gender": "女",
        "subjects": "数学,英语",
        "grades": "初二,初三",
        "teaching_mode": "线下,线上",
        "fee": 90,
        "introduction": "初中数英双科辅导，提分路径清晰",
        "wechat": "tutorG007",
        "teaching_time": {"周六": {"start": "09:30", "end": "12:30"}},
    },
    {
        "nickname": "家教_六年级数学_H",
        "gender": "男",
        "subjects": "数学",
        "grades": "五年级,六年级",
        "teaching_mode": "线上",
        "fee": 80,
        "introduction": "小学高段数学网课，讲解清晰有耐心",
        "wechat": "tutorH008",
        "teaching_time": {"周六": {"start": "19:00", "end": "21:00"}, "周日": {"start": "10:00", "end": "12:00"}},
    },
    {
        "nickname": "家教_高一化学_I",
        "gender": "女",
        "subjects": "化学",
        "grades": "高一,高二",
        "teaching_mode": "线上,线下",
        "fee": 110,
        "introduction": "高中化学专题突破，善于归纳易错点",
        "wechat": "tutorI009",
        "teaching_time": {"周六": {"start": "13:30", "end": "16:00"}},
    },
    {
        "nickname": "家教_高二物理_J",
        "gender": "女",
        "subjects": "物理",
        "grades": "高二,高三",
        "teaching_mode": "线下,线上",
        "fee": 140,
        "introduction": "高中物理模型化教学，长期跟进效果好",
        "wechat": "tutorJ010",
        "teaching_time": {"周六": {"start": "15:30", "end": "18:30"}},
    },
]


def ensure_user(nickname, role, index):
    user = User.query.filter_by(nickname=nickname).first()
    if not user:
        user = User(
            nickname=nickname,
            phone=f"1880000{index:04d}",
            email=f"seed_{index}@example.com",
            role=role,
            is_active=True,
        )
        user.set_password(DEFAULT_PASSWORD)
        db.session.add(user)
        db.session.flush()
        return user, True

    user.role = role
    user.is_active = True
    if not user.phone:
        user.phone = f"1880000{index:04d}"
    if not user.email:
        user.email = f"seed_{index}@example.com"
    user.set_password(DEFAULT_PASSWORD)
    db.session.flush()
    return user, False


def upsert_student(data, index):
    user, created_user = ensure_user(data["nickname"], "student", index)
    info = StudentInfo.query.filter_by(user_id=user.id).first()
    created_info = info is None
    if info is None:
        info = StudentInfo(user_id=user.id)
        db.session.add(info)

    info.gender = data["gender"]
    info.subjects = data["subjects"]
    info.grade = data["grade"]
    info.teaching_mode = data["teaching_mode"]
    info.budget_upper = data["budget_upper"]
    info.teaching_time = json.dumps(data.get("teaching_time", {}), ensure_ascii=False)
    info.requirements = data.get("requirements", "")[:50]
    info.wechat = data.get("wechat", "")
    info.accept_opposite_gender = True
    return created_user, created_info


def upsert_tutor(data, index):
    user, created_user = ensure_user(data["nickname"], "tutor", 100 + index)
    info = TutorInfo.query.filter_by(user_id=user.id).first()
    created_info = info is None
    if info is None:
        info = TutorInfo(user_id=user.id)
        db.session.add(info)

    info.gender = data["gender"]
    info.subjects = data["subjects"]
    info.grades = data["grades"]
    info.teaching_mode = data["teaching_mode"]
    info.fee = data["fee"]
    info.teaching_time = json.dumps(data.get("teaching_time", {}), ensure_ascii=False)
    info.introduction = data["introduction"][:50]
    info.wechat = data.get("wechat", "")
    info.accept_opposite_gender = True
    return created_user, created_info


def main():
    with app.app_context():
        db.create_all()

        created_users = 0
        created_student_infos = 0
        created_tutor_infos = 0

        for i, item in enumerate(STUDENT_SEED, 1):
            c_user, c_info = upsert_student(item, i)
            created_users += int(c_user)
            created_student_infos += int(c_info)

        for i, item in enumerate(TUTOR_SEED, 1):
            c_user, c_info = upsert_tutor(item, i)
            created_users += int(c_user)
            created_tutor_infos += int(c_info)

        db.session.commit()

        print("=== Seed Completed ===")
        print(f"students_seeded={len(STUDENT_SEED)}")
        print(f"tutors_seeded={len(TUTOR_SEED)}")
        print(f"users_created={created_users}")
        print(f"student_infos_created={created_student_infos}")
        print(f"tutor_infos_created={created_tutor_infos}")
        print(f"users_total={User.query.count()}")
        print(f"students_total={StudentInfo.query.count()}")
        print(f"tutors_total={TutorInfo.query.count()}")
        print("default_password_for_seed_users=test12345")


if __name__ == "__main__":
    main()
