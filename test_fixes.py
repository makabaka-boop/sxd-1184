import requests
import json

BASE_URL = "http://localhost:8124"

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login",
                      data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]

def test_fixes():
    print("=" * 60)
    print("验证三个问题修复")
    print("=" * 60)

    admin_token = login("admin", "admin123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    t1_token = login("taster1", "taster123")
    t1_headers = {"Authorization": f"Bearer {t1_token}"}

    # ====== 准备数据 ======
    print("\n【准备测试数据】")

    # 创建原料组
    r = requests.post(f"{BASE_URL}/ingredient-groups/", headers=admin_headers,
                      json={"name": "测试基底组", "ingredients": "测试原料"})
    group_id = r.json()["id"]
    print(f"原料组 ID: {group_id}")

    # 创建配方
    r = requests.post(f"{BASE_URL}/recipes/", headers=admin_headers,
                      json={"name": "测试配方", "version": "v1.0",
                            "ingredient_group_id": group_id})
    recipe_id = r.json()["id"]
    print(f"配方 ID: {recipe_id}, 版本: v1.0")

    # 创建批次1
    r = requests.post(f"{BASE_URL}/batches/", headers=admin_headers,
                      json={"batch_no": "TEST-BATCH-001", "recipe_id": recipe_id})
    batch1_id = r.json()["id"]
    print(f"批次1 ID: {batch1_id}")

    # 创建批次2（同一配方版本）
    r = requests.post(f"{BASE_URL}/batches/", headers=admin_headers,
                      json={"batch_no": "TEST-BATCH-002", "recipe_id": recipe_id})
    batch2_id = r.json()["id"]
    print(f"批次2 ID: {batch2_id}")

    # 创建另一个版本的配方和批次，用于测试版本筛选
    r = requests.post(f"{BASE_URL}/recipes/", headers=admin_headers,
                      json={"name": "测试配方", "version": "v2.0",
                            "ingredient_group_id": group_id})
    recipe2_id = r.json()["id"]
    print(f"配方2 ID: {recipe2_id}, 版本: v2.0")

    r = requests.post(f"{BASE_URL}/batches/", headers=admin_headers,
                      json={"batch_no": "TEST-BATCH-V2", "recipe_id": recipe2_id})
    batch_v2_id = r.json()["id"]
    print(f"v2批次 ID: {batch_v2_id}")

    # ====== 问题1：验证配方维度的评审去重 ======
    print("\n" + "=" * 60)
    print("【问题1验证】同一配方版本同一轮次不可重复提交有效评审")
    print("=" * 60)

    # 完成两个批次的试配并开启评审
    for bid in [batch1_id, batch2_id]:
        requests.post(f"{BASE_URL}/batches/{bid}/finish-trial", headers=admin_headers)
        requests.post(f"{BASE_URL}/batches/{bid}/start-review", headers=admin_headers)
    print("两个批次都已进入评审中状态")

    # 评审员1给批次1提交有效评审
    r = requests.post(f"{BASE_URL}/reviews", headers=t1_headers,
                      json={"batch_id": batch1_id, "sweetness": 7.0,
                            "consistency": 7.0, "melt_speed": 7.0,
                            "is_valid": True})
    print(f"\n评审员1给批次1提交有效评审: {r.status_code} - {'成功' if r.status_code == 200 else r.json().get('detail')}")

    # 评审员1再给批次2提交有效评审（同一配方同一轮次，应该被拒绝）
    r = requests.post(f"{BASE_URL}/reviews", headers=t1_headers,
                      json={"batch_id": batch2_id, "sweetness": 8.0,
                            "consistency": 8.0, "melt_speed": 8.0,
                            "is_valid": True})
    print(f"评审员1给批次2提交有效评审: {r.status_code} - {r.json().get('detail')}")

    # 验证：应该被拒绝
    if r.status_code == 400 and "配方版本" in r.json().get("detail", ""):
        print("✅ 修复验证通过：同一配方版本同一轮次不可重复提交有效评审")
    else:
        print("❌ 修复验证失败")

    # 提交无效评审应该可以
    r = requests.post(f"{BASE_URL}/reviews", headers=t1_headers,
                      json={"batch_id": batch2_id, "sweetness": 5.0,
                            "consistency": 5.0, "melt_speed": 5.0,
                            "is_valid": False, "taste_description": "测试无效评审"})
    print(f"\n评审员1给批次2提交无效评审: {r.status_code} - {'成功' if r.status_code == 200 else r.json().get('detail')}")

    # ====== 问题2：验证版本筛选 ======
    print("\n" + "=" * 60)
    print("【问题2验证】按版本、状态等筛选条件")
    print("=" * 60)

    # 测试按配方版本筛选批次
    r = requests.get(f"{BASE_URL}/batches/", params={"recipe_version": "v1.0"},
                     headers=admin_headers)
    batches = r.json()
    print(f"\n按版本 v1.0 筛选批次，结果数: {len(batches)}")
    v1_batch_nos = [b["batch_no"] for b in batches]
    print(f"  批次列表: {v1_batch_nos}")

    if len(batches) == 2 and all("BATCH-00" in b["batch_no"] for b in batches):
        print("✅ 按配方版本筛选批次生效")
    else:
        print("❌ 按配方版本筛选批次未生效")

    # 测试按状态筛选（评审中 vs 待试配）
    r = requests.get(f"{BASE_URL}/batches/", params={"status": "评审中"},
                     headers=admin_headers)
    reviewing_batches = r.json()
    print(f"\n按状态'评审中'筛选批次，结果数: {len(reviewing_batches)}")

    # v2的批次应该是待试配状态，不在结果中
    has_v2 = any("V2" in b["batch_no"] for b in reviewing_batches)
    if not has_v2 and len(reviewing_batches) == 2:
        print("✅ 按状态筛选批次生效")
    else:
        print("❌ 按状态筛选批次未生效")

    # ====== 问题3：验证统计排除已终止/已定版 ======
    print("\n" + "=" * 60)
    print("【问题3验证】统计排除已定版、已终止批次")
    print("=" * 60)

    # 先看当前的待评审统计
    r = requests.get(f"{BASE_URL}/stats/pending-batches", headers=admin_headers)
    stats_before = r.json()
    print(f"\n终止前列队统计: total={stats_before['total']}, by_status={stats_before['by_status']}")

    # 终止批次2
    r = requests.post(f"{BASE_URL}/batches/{batch2_id}/terminate", headers=admin_headers)
    print(f"\n终止批次2: {r.status_code}")

    # 再看统计
    r = requests.get(f"{BASE_URL}/stats/pending-batches", headers=admin_headers)
    stats_after = r.json()
    print(f"终止后列队统计: total={stats_after['total']}, by_status={stats_after['by_status']}")

    # 验证 by_status 中没有已终止状态
    if "已终止" not in stats_after["by_status"] and stats_after["total"] == 2:
        print("✅ 待评审批次统计已排除已终止状态")
    else:
        print("❌ 待评审批次统计未正确排除已终止状态")

    # 终止 v2 批次，然后测试配方稳定度是否排除已终止的
    # 先给 v2 批次提交一些评审
    requests.post(f"{BASE_URL}/batches/{batch_v2_id}/finish-trial", headers=admin_headers)
    requests.post(f"{BASE_URL}/batches/{batch_v2_id}/start-review", headers=admin_headers)

    # 用其他评审员给v2批次提交评审
    t2_token = login("taster2", "taster123")
    t2_headers = {"Authorization": f"Bearer {t2_token}"}
    t3_token = login("taster3", "taster123")
    t3_headers = {"Authorization": f"Bearer {t3_token}"}

    for headers in [t2_headers, t3_headers]:
        requests.post(f"{BASE_URL}/reviews", headers=headers,
                      json={"batch_id": batch_v2_id, "sweetness": 6.0,
                            "consistency": 6.0, "melt_speed": 6.0,
                            "is_valid": True, "defect_reason": "测试缺陷"})

    # 终止v2批次
    requests.post(f"{BASE_URL}/batches/{batch_v2_id}/terminate", headers=admin_headers)
    print(f"\nv2批次已终止，包含2条有效评审")

    # 测试默认排除已终止
    r = requests.get(f"{BASE_URL}/stats/recipe-stability", headers=admin_headers)
    stability = r.json()
    v2_versions = [s for s in stability if s["version"] == "v2.0"]
    print(f"配方稳定度（默认排除已终止）: v2版本数量 = {len(v2_versions)}")

    # v2.0的批次已终止，但配方本身还在，只是评审数应该为0或者不出现在列表中？
    # 因为我们排除了已终止批次的评审，所以v2配方的评审数可能为0
    if len(v2_versions) == 0:
        print("✅ 配方稳定度统计已排除已终止批次的评审")
    else:
        # 如果还在列表中，检查评审数是否为0
        if v2_versions[0]["review_count"] == 0:
            print("✅ 配方稳定度统计已排除已终止批次的评审")
        else:
            print(f"❌ 配方稳定度统计未排除已终止批次的评审, review_count={v2_versions[0]['review_count']}")

    # 测试不排除的情况
    r = requests.get(f"{BASE_URL}/stats/recipe-stability",
                     params={"exclude_terminated": "false"},
                     headers=admin_headers)
    stability_all = r.json()
    v2_all = [s for s in stability_all if s["version"] == "v2.0"]
    print(f"配方稳定度（不排除已终止）: v2版本 review_count = {v2_all[0]['review_count'] if v2_all else 0}")

    if v2_all and v2_all[0]["review_count"] == 2:
        print("✅ exclude_terminated=false 时包含已终止批次的评审")
    else:
        print("❌ exclude_terminated=false 时未包含已终止批次的评审")

    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)

if __name__ == "__main__":
    test_fixes()
