import requests
import json

BASE_URL = "http://localhost:8124"

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login",
                      data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]

def test_full_flow():
    print("=== 1. 登录 ===")
    token = login("admin", "admin123")
    headers = {"Authorization": f"Bearer {token}"}
    print(f"获取token成功: {token[:30]}...")

    print("\n=== 2. 创建原料组 ===")
    r = requests.post(f"{BASE_URL}/ingredient-groups/", headers=headers,
                      json={"name": "香草基底组", "description": "香草口味冰淇淋原料",
                            "ingredients": "鲜奶,奶油,香草精,糖"})
    print(f"状态码: {r.status_code}, 响应: {json.dumps(r.json(), ensure_ascii=False)}")
    group_id = r.json()["id"]

    print("\n=== 3. 创建配方版本 ===")
    r = requests.post(f"{BASE_URL}/recipes/", headers=headers,
                      json={"name": "香草冰淇淋", "version": "v1.0",
                            "ingredient_group_id": group_id,
                            "description": "经典香草口味",
                            "formula_details": "鲜奶60%,奶油25%,糖10%,香草精5%"})
    print(f"状态码: {r.status_code}, 响应: {json.dumps(r.json(), ensure_ascii=False)}")
    recipe_id = r.json()["id"]

    print("\n=== 4. 创建试配批次 ===")
    r = requests.post(f"{BASE_URL}/batches/", headers=headers,
                      json={"batch_no": "BATCH-2024-001", "recipe_id": recipe_id,
                            "responsible_id": 1, "notes": "首次试配"})
    print(f"状态码: {r.status_code}, 响应: {json.dumps(r.json(), ensure_ascii=False)}")
    batch_id = r.json()["id"]

    print("\n=== 5. 完成试配 ===")
    r = requests.post(f"{BASE_URL}/batches/{batch_id}/finish-trial", headers=headers)
    print(f"状态码: {r.status_code}, 状态: {r.json()['status']}")

    print("\n=== 6. 开启评审 ===")
    r = requests.post(f"{BASE_URL}/batches/{batch_id}/start-review", headers=headers)
    print(f"状态码: {r.status_code}, 状态: {r.json()['status']}, 轮次: {r.json()['round_no']}")

    print("\n=== 7. 三个评审员提交评审 ===")
    for i, username in enumerate(["taster1", "taster2", "taster3"], 1):
        t_token = login(username, "taster123")
        t_headers = {"Authorization": f"Bearer {t_token}"}
        sweetness = 6.0 + i
        consistency = 5.0 + i * 0.5
        melt_speed = 7.0 - i * 0.3
        r = requests.post(f"{BASE_URL}/reviews", headers=t_headers,
                          json={"batch_id": batch_id, "sweetness": sweetness,
                                "consistency": consistency, "melt_speed": melt_speed,
                                "taste_description": f"品鉴师{i}号的口感描述",
                                "defect_reason": "甜度稍低" if i < 3 else None,
                                "suggested_action": "增加糖量" if i < 3 else None,
                                "is_valid": True})
        print(f"  评审员{i}: 状态{r.status_code} - {'成功' if r.status_code == 200 else r.json().get('detail')}")

    print("\n=== 8. 验证同一人不能重复提交有效评审 ===")
    t_token = login("taster1", "taster123")
    t_headers = {"Authorization": f"Bearer {t_token}"}
    r = requests.post(f"{BASE_URL}/reviews", headers=t_headers,
                      json={"batch_id": batch_id, "sweetness": 7.0,
                            "consistency": 6.0, "melt_speed": 7.0,
                            "is_valid": True})
    print(f"  重复提交: 状态{r.status_code} - {r.json().get('detail')}")

    print("\n=== 9. 统计 - 待评审批次 ===")
    r = requests.get(f"{BASE_URL}/stats/pending-batches", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

    print("\n=== 10. 统计 - 缺陷原因分布 ===")
    r = requests.get(f"{BASE_URL}/stats/defect-distribution", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

    print("\n=== 11. 统计 - 配方稳定度 ===")
    r = requests.get(f"{BASE_URL}/stats/recipe-stability", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

    print("\n=== 12. 异常检测 ===")
    r = requests.get(f"{BASE_URL}/stats/anomalies", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

    print("\n=== 13. 提交调整记录 ===")
    r = requests.post(f"{BASE_URL}/batches/{batch_id}/adjustments", headers=headers,
                      json={"adjustment_details": "增加5%的糖量", "next_round_scheduled": False})
    print(f"状态码: {r.status_code}")
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

    print("\n=== 14. 检测-调整后未开启新轮次 ===")
    r = requests.get(f"{BASE_URL}/stats/anomalies/missing-next-round", headers=headers)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_full_flow()
