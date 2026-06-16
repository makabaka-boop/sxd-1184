import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8124"

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login",
                      data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]

def test_risk_feature():
    print("=== 研发任务进度风险提示功能测试 ===\n")

    print("=== 1. 登录 ===")
    token = login("admin", "admin123")
    headers = {"Authorization": f"Bearer {token}"}
    print(f"获取token成功\n")

    print("=== 2. 创建原料组 ===")
    r = requests.post(f"{BASE_URL}/ingredient-groups/", headers=headers,
                      json={"name": "巧克力基底组", "description": "巧克力口味",
                            "ingredients": "鲜奶,奶油,可可粉,糖"})
    group_id = r.json()["id"]
    print(f"原料组ID: {group_id}\n")

    print("=== 3. 创建配方 ===")
    r = requests.post(f"{BASE_URL}/recipes/", headers=headers,
                      json={"name": "巧克力冰淇淋", "version": "v1.0",
                            "ingredient_group_id": group_id})
    recipe_id = r.json()["id"]
    print(f"配方ID: {recipe_id}\n")

    print("=== 4. 创建试配批次 ===")
    r = requests.post(f"{BASE_URL}/batches/", headers=headers,
                      json={"batch_no": "RISK-TEST-001", "recipe_id": recipe_id,
                            "responsible_id": 1})
    batch_id = r.json()["id"]
    print(f"批次ID: {batch_id}\n")

    print("=== 5. 创建研发任务（设置3天后的目标日期） ===")
    target_date = (datetime.utcnow() + timedelta(days=3)).isoformat()
    r = requests.post(f"{BASE_URL}/rd-tasks/", headers=headers,
                      json={
                          "title": "巧克力冰淇淋研发",
                          "description": "测试风险状态功能",
                          "priority": "高",
                          "target_date": target_date,
                          "responsible_id": 1,
                          "batch_ids": [batch_id]
                      })
    task_id = r.json()["id"]
    print(f"任务ID: {task_id}")
    print(f"风险状态: {r.json()['risk_status']}")
    print(f"风险原因: {r.json()['risk_reason']}\n")

    print("=== 6. 查看任务列表（验证风险状态） ===")
    r = requests.get(f"{BASE_URL}/rd-tasks/", headers=headers)
    tasks = r.json()
    for task in tasks:
        print(f"任务: {task['title']}, 风险状态: {task['risk_status']}, 原因: {task['risk_reason']}")
    print()

    print("=== 7. 完成试配 ===")
    r = requests.post(f"{BASE_URL}/batches/{batch_id}/finish-trial", headers=headers)
    print(f"批次状态: {r.json()['status']}\n")

    print("=== 8. 刷新任务风险状态 ===")
    r = requests.post(f"{BASE_URL}/rd-tasks/{task_id}/refresh-risk", headers=headers)
    print(f"刷新后风险状态: {r.json()['risk_status']}")
    print(f"刷新后风险原因: {r.json()['risk_reason']}\n")

    print("=== 9. 开启评审 ===")
    r = requests.post(f"{BASE_URL}/batches/{batch_id}/start-review", headers=headers)
    print(f"批次状态: {r.json()['status']}\n")

    print("=== 10. 仅1人提交评审（验证评审人数不足风险） ===")
    t_token = login("taster1", "taster123")
    t_headers = {"Authorization": f"Bearer {t_token}"}
    r = requests.post(f"{BASE_URL}/reviews", headers=t_headers,
                      json={"batch_id": batch_id, "sweetness": 7.0,
                            "consistency": 6.0, "melt_speed": 5.0,
                            "is_valid": True})
    print(f"评审提交成功\n")

    print("=== 11. 查看任务详情（验证风险状态） ===")
    r = requests.get(f"{BASE_URL}/rd-tasks/{task_id}", headers=headers)
    task_detail = r.json()
    print(f"风险状态: {task_detail['risk_status']}")
    print(f"风险原因: {task_detail['risk_reason']}\n")

    print("=== 12. 另外2人提交评审 ===")
    for username in ["taster2", "taster3"]:
        t_token = login(username, "taster123")
        t_headers = {"Authorization": f"Bearer {t_token}"}
        r = requests.post(f"{BASE_URL}/reviews", headers=t_headers,
                          json={"batch_id": batch_id, "sweetness": 8.0,
                                "consistency": 7.0, "melt_speed": 6.0,
                                "is_valid": True})
    print("评审提交完成\n")

    print("=== 13. 刷新风险状态（评审人数满足后应为正常） ===")
    r = requests.post(f"{BASE_URL}/rd-tasks/{task_id}/refresh-risk", headers=headers)
    print(f"风险状态: {r.json()['risk_status']}")
    print(f"风险原因: {r.json()['risk_reason']}\n")

    print("=== 14. 提交调整但不安排下一轮（验证需关注风险） ===")
    r = requests.post(f"{BASE_URL}/batches/{batch_id}/adjustments", headers=headers,
                      json={"adjustment_details": "调整配方", "next_round_scheduled": False})
    print(f"调整提交成功\n")

    print("=== 15. 刷新风险状态 ===")
    r = requests.post(f"{BASE_URL}/rd-tasks/{task_id}/refresh-risk", headers=headers)
    print(f"风险状态: {r.json()['risk_status']}")
    print(f"风险原因: {r.json()['risk_reason']}\n")

    print("=== 16. 风险统计分析 - 按负责人 ===")
    r = requests.get(f"{BASE_URL}/stats/tasks/risk-by-responsible", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    print()

    print("=== 17. 风险统计分析 - 按任务阶段 ===")
    r = requests.get(f"{BASE_URL}/stats/tasks/risk-by-stage", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    print()

    print("=== 18. 风险统计分析 - 按优先级 ===")
    r = requests.get(f"{BASE_URL}/stats/tasks/risk-by-priority", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    print()

    print("=== 19. 风险统计分析 - 总览 ===")
    r = requests.get(f"{BASE_URL}/stats/tasks/risk-overview", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    print()

    print("=== 20. 按风险状态筛选任务（筛选'需关注'） ===")
    r = requests.get(f"{BASE_URL}/rd-tasks/?risk_status=需关注", headers=headers)
    tasks = r.json()
    print(f"找到 {len(tasks)} 个'需关注'的任务")
    for task in tasks:
        print(f"  - {task['title']}: {task['risk_reason']}")
    print()

    print("=== 21. 刷新所有任务风险状态 ===")
    r = requests.post(f"{BASE_URL}/rd-tasks/refresh-all-risk", headers=headers)
    print(r.json())
    print()

    print("=== 测试完成 ===")

if __name__ == "__main__":
    test_risk_feature()
