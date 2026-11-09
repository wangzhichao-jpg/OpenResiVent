"""对示例噪声源、损失及房间修正做独立 ±3 dB 扰动。"""

import copy
from pathlib import Path

import yaml

from openresivent.duct.noise import calculate_noise

ROOT = Path(__file__).resolve().parents[1]


def sensitivity(d):
    """逐个物理输入扰动，返回 A 声级变化 dB。"""
    q = d["reference_flow_m3_s"]
    base = calculate_noise(d, q)["a_weighted_db"]
    rows = []

    def run(label, mutate):
        values = []
        for shift in (-3, 3):
            z = copy.deepcopy(d)
            mutate(z, shift)
            values.append(calculate_noise(z, q)["a_weighted_db"] - base)
        rows.append((label, *values))

    run("风机频谱", lambda z, s: z.update(fan_power_db=[v + s for v in z["fan_power_db"]]))
    for i, stage in enumerate(d["stages"]):
        run(
            f"{stage['kind']}衰减",
            lambda z, s, i=i: z["stages"][i].update(
                attenuation_db=[max(0, v + s) for v in z["stages"][i]["attenuation_db"]]
            ),
        )
        if stage.get("regenerated_db") is not None:
            run(
                f"{stage['kind']}再生声",
                lambda z, s, i=i: z["stages"][i].update(
                    regenerated_db=[v + s for v in z["stages"][i]["regenerated_db"]]
                ),
            )
    run(
        "末端反射",
        lambda z, s: z.update(
            terminal_reflection_db=[max(0, v + s) for v in z["terminal_reflection_db"]]
        ),
    )
    run(
        "风口再生声",
        lambda z, s: z.update(
            diffuser_regenerated_db=[v + s for v in z["diffuser_regenerated_db"]]
        ),
    )
    # 指向因子和混响项分别按声强比 ±3 dB 缩放，避免错误地对长度加 dB。
    run("直达声指向因子", lambda z, s: z.update(directivity=z["directivity"] * 10 ** (s / 10)))
    run("混响声项", lambda z, s: z.update(room_constant_m2=z["room_constant_m2"] / 10 ** (s / 10)))
    return base, rows


def main():
    d = yaml.safe_load((ROOT / "cases/book/ch04/ex4-09.yaml").read_text())["input"]
    base, rows = sensitivity(d)
    out = ROOT / "build/parameter-sweep/noise_sensitivity.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"基准 {base:.4f} dB(A)；每次只改变一组，衰减下限截断为零。",
        "",
        "| 输入 | −3 dB 改变后差值 | +3 dB 改变后差值 |",
        "|---|---:|---:|",
    ]
    lines.extend(f"| {k} | {a:.6f} | {b:.6f} |" for k, a, b in rows)
    out.write_text("\n".join(lines) + "\n")
    print(out)


if __name__ == "__main__":
    main()
