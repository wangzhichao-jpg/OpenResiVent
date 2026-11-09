"""OpenCFD v2512 独立编写的算例字典生成，不包含 OpenFOAM 源码。"""

import math
from dataclasses import dataclass
from pathlib import Path

from openresivent.cfd.config import case_root

HEADER = "// OpenResiVent 自行编写；OpenFOAM 作为外部进程，非官方教程文件。\n"


def dictionary(name: str, body: str, cls: str = "dictionary") -> str:
    """OpenFOAM 对象名称、文本和类型 → 自行编写的字典。"""
    return (
        HEADER
        + f"FoamFile\n{{ version 2.0; format ascii; class {cls}; object {name}; }}\n"
        + body
        + "\n"
    )


@dataclass(frozen=True)
class Room:
    """房间及两端墙矩形风口尺寸/中心坐标 m、入口体积流量 m³/s。"""

    length: float = 4
    width: float = 3
    height: float = 2.5
    opening: float = 0.5
    flow: float = 0.05
    outlet: str = "upper"
    mesh_scale: int = 1
    inlet_y: float | None = None
    outlet_y: float | None = None
    inlet_z: float | None = None
    outlet_z: float | None = None
    outlet_opening: float | None = None
    inlet_height: float | None = None
    outlet_height: float | None = None


def room_mesh(c: Room) -> str:
    """生成风口位于两端墙且横向居中的分块网格字典。"""
    if (
        min(c.length, c.width, c.height, c.opening, c.flow) <= 0
        or c.width <= c.opening
        or c.height <= 2 * c.opening
        or c.outlet not in ("upper", "lower")
        or c.mesh_scale < 1
    ):
        raise ValueError("房间参数无效")
    outsize = c.outlet_opening if c.outlet_opening is not None else c.opening
    ih = c.inlet_height if c.inlet_height is not None else c.opening
    oh = c.outlet_height if c.outlet_height is not None else outsize
    iy = c.inlet_y if c.inlet_y is not None else c.width / 2
    oy = c.outlet_y if c.outlet_y is not None else c.width / 2
    iz = c.inlet_z if c.inlet_z is not None else c.height - ih / 2
    oz = (
        c.outlet_z
        if c.outlet_z is not None
        else (c.height - oh / 2 if c.outlet == "upper" else oh / 2)
    )
    if min(outsize, ih, oh) <= 0 or not (
        c.opening / 2 <= iy <= c.width - c.opening / 2
        and ih / 2 <= iz <= c.height - ih / 2
        and outsize / 2 <= oy <= c.width - outsize / 2
        and oh / 2 <= oz <= c.height - oh / 2
    ):
        raise ValueError("风口位置或尺寸超出墙面")
    xs = [0, c.length]
    ys = sorted(
        {0, c.width, iy - c.opening / 2, iy + c.opening / 2, oy - outsize / 2, oy + outsize / 2}
    )
    zs = sorted(
        {
            0,
            c.opening,
            c.height - c.opening,
            c.height,
            iz - ih / 2,
            iz + ih / 2,
            oz - oh / 2,
            oz + oh / 2,
        }
    )
    idx = lambda i, j, k: i * len(ys) * len(zs) + j * len(zs) + k
    vertices = [f"({x:g} {y:g} {z:g})" for x in xs for y in ys for z in zs]
    blocks = []
    inlet = []
    outlet = []
    walls = []
    h = 0.25 / c.mesh_scale
    for j in range(len(ys) - 1):
        for k in range(len(zs) - 1):
            a = idx(0, j, k)
            b = idx(1, j, k)
            d = idx(0, j + 1, k)
            e = idx(1, j + 1, k)
            v = (a, b, e, d, a + 1, b + 1, e + 1, d + 1)
            cells = (
                max(1, round(c.length / h)),
                max(1, round((ys[j + 1] - ys[j]) / h)),
                max(1, round((zs[k + 1] - zs[k]) / h)),
            )
            blocks.append(
                "hex ("
                + " ".join(map(str, v))
                + ") ("
                + " ".join(map(str, cells))
                + ") simpleGrading (1 1 1)"
            )
            left = (a, a + 1, d + 1, d)
            right = (b, e, e + 1, b + 1)
            ym = (ys[j] + ys[j + 1]) / 2
            zm = (zs[k] + zs[k + 1]) / 2
            (inlet if abs(ym - iy) < c.opening / 2 and abs(zm - iz) < ih / 2 else walls).append(
                left
            )
            (outlet if abs(ym - oy) < outsize / 2 and abs(zm - oz) < oh / 2 else walls).append(
                right
            )
            if j == 0:
                walls.append((a, b, b + 1, a + 1))
            if j == len(ys) - 2:
                walls.append((d, d + 1, e + 1, e))
            if k == 0:
                walls.append((a, d, e, b))
            if k == len(zs) - 2:
                walls.append((a + 1, b + 1, e + 1, d + 1))
    face = lambda fs: " ".join("(" + " ".join(map(str, f)) + ")" for f in fs)
    return dictionary(
        "blockMeshDict",
        "scale 1;\nvertices ("
        + " ".join(vertices)
        + ");\nblocks ("
        + " ".join(blocks)
        + ");\nedges ();\nboundary (inlet {type patch; faces ("
        + face(inlet)
        + ");} outlet {type patch; faces ("
        + face(outlet)
        + ");} walls {type wall; faces ("
        + face(walls)
        + ");});\nmergePatchPairs ();",
    )


def _field(name, dimensions, internal, inlet, outlet, wall):
    return dictionary(
        name,
        f"dimensions {dimensions};\ninternalField uniform {internal};\nboundaryField {{ inlet {{{inlet}}} outlet {{{outlet}}} walls {{{wall}}} }}",
        "volVectorField" if name == "U" else "volScalarField",
    )


def create_room(
    path: Path,
    c: Room,
    *,
    diffusivity: float = 0.005,
    iterations: int = 1000,
    heat_w: float = 0,
    scheme: str = "second",
) -> Path:
    """生成 k-ε、被动空气龄及可选均匀被动热源：扩散 m²/s、热源 W；不覆盖。"""
    if diffusivity <= 0 or iterations < 1 or heat_w < 0 or scheme not in ("first", "second"):
        raise ValueError("扩散系数和迭代数须为正")
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    for sub in ("0", "constant", "system"):
        (path / sub).mkdir()
    speed = c.flow / (c.opening * (c.inlet_height if c.inlet_height is not None else c.opening))
    files = {
        "system/blockMeshDict": room_mesh(c),
        "0/U": _field(
            "U",
            "[0 1 -1 0 0 0 0]",
            "(0 0 0)",
            f"type fixedValue; value uniform ({speed:g} 0 0);",
            "type zeroGradient;",
            "type noSlip;",
        ),
        "0/p": _field(
            "p",
            "[0 2 -2 0 0 0 0]",
            "0",
            "type zeroGradient;",
            "type fixedValue; value uniform 0;",
            "type zeroGradient;",
        ),
        "0/k": _field(
            "k",
            "[0 2 -2 0 0 0 0]",
            "0.001",
            "type fixedValue; value uniform 0.001;",
            "type inletOutlet; inletValue uniform 0.001; value uniform 0.001;",
            "type kqRWallFunction; value uniform 0.001;",
        ),
        "0/epsilon": _field(
            "epsilon",
            "[0 2 -3 0 0 0 0]",
            "0.0001",
            "type fixedValue; value uniform 0.0001;",
            "type inletOutlet; inletValue uniform 0.0001; value uniform 0.0001;",
            "type epsilonWallFunction; value uniform 0.0001;",
        ),
        "0/nut": _field(
            "nut",
            "[0 2 -1 0 0 0 0]",
            "0",
            "type calculated; value uniform 0;",
            "type calculated; value uniform 0;",
            "type nutkWallFunction; value uniform 0;",
        ),
        "0/T": _field(
            "T",
            "[0 0 1 0 0 0 0]",
            "0",
            "type fixedValue; value uniform 0;",
            "type zeroGradient;",
            "type zeroGradient;",
        ),
        "constant/transportProperties": dictionary(
            "transportProperties",
            f"transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] 1.5e-5;\nDT [0 2 -1 0 0 0 0] {diffusivity:g};",
        ),
        "constant/turbulenceProperties": dictionary(
            "turbulenceProperties",
            "simulationType RAS;\nRAS { RASModel kEpsilon; turbulence on; printCoeffs on; }",
        ),
        "constant/fvOptions": dictionary(
            "fvOptions",
            "ageSource { type scalarSemiImplicitSource; active true; selectionMode all; volumeMode specific; sources { T (1 0); } }",
        ),
        "system/fvSchemes": dictionary(
            "fvSchemes",
            "ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\ndivSchemes { default none; div(phi,U) bounded Gauss upwind; div(phi,k) bounded Gauss upwind; div(phi,epsilon) bounded Gauss upwind; div(phi,T) Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear; }\nlaplacianSchemes { default Gauss linear corrected; }\ninterpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\nwallDist { method meshWave; }",
        ),
        "system/fvSolution": dictionary(
            "fvSolution",
            "solvers { p { solver GAMG; tolerance 1e-7; relTol 0.01; smoother GaussSeidel; } U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-7; relTol 0.01; } k { $U; } epsilon { $U; } T { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0; maxIter 20000; } }\nSIMPLE { pRefCell 0; pRefValue 0; nNonOrthogonalCorrectors 0; residualControl { p 1e-5; U 1e-6; k 1e-6; epsilon 1e-6; } }\nrelaxationFactors { fields { p 0.3; } equations { U 0.7; k 0.7; epsilon 0.7; T 0.3; } }",
        ),
        "system/controlDict": dictionary(
            "controlDict",
            f"application simpleFoam; startFrom startTime; startTime 0; stopAt endTime; endTime {iterations}; deltaT 1; writeControl timeStep; writeInterval {iterations}; writeFormat ascii; writePrecision 10; runTimeModifiable false;",
        ),
        "system/controlDict.age": dictionary(
            "controlDict",
            "application scalarTransportFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 10000; deltaT 10; writeControl timeStep; writeInterval 1000; writeFormat ascii; writePrecision 10; runTimeModifiable false;",
        ),
        "README.md": f"# 房间通风示例\n\n自拟示例；尺寸 {c.length}×{c.width}×{c.height} m，入口 {c.flow} m³/s，出口 {c.outlet}；OpenCFD v2512，k-ε，运动黏度1.5e-5 m²/s，均匀有效标量扩散系数 {diffusivity} m²/s。\n空气龄满足 div(U τ) − div(D grad τ) = 1；入口 τ=0、出口与壁面零梯度。内热源未建模，等温不可压缩。\n",
    }
    if heat_w:
        rho_cp = 1.2 * 1006
        source = heat_w / (rho_cp * c.length * c.width * c.height)
        files["0/T.thermal"] = _field(
            "T",
            "[0 0 0 1 0 0 0]",
            "293.15",
            "type fixedValue; value uniform 293.15;",
            "type zeroGradient;",
            "type zeroGradient;",
        )
        files["constant/fvOptions.thermal"] = dictionary(
            "fvOptions",
            f"thermalSource {{ type scalarSemiImplicitSource; active true; selectionMode all; volumeMode specific; sources {{ T ({source:.12g} 0); }} }}",
        )
        files["README.md"] += (
            f"\n被动温度场均匀热源 {heat_w} W，ρ=1.2 kg/m³、cp=1006 J/(kg K)，流场冻结不考虑热浮力；非热舒适或火灾计算。\n"
        )
    if scheme == "second":
        files["system/fvSchemes"] = (
            files["system/fvSchemes"]
            .replace(
                "div(phi,U) bounded Gauss upwind;", "div(phi,U) bounded Gauss linearUpwind grad(U);"
            )
            .replace(
                "div(phi,k) bounded Gauss upwind;", "div(phi,k) bounded Gauss limitedLinear 1;"
            )
            .replace(
                "div(phi,epsilon) bounded Gauss upwind;",
                "div(phi,epsilon) bounded Gauss limitedLinear 1;",
            )
            .replace("div(phi,T) Gauss upwind;", "div(phi,T) bounded Gauss limitedLinear 1;")
        )
    files["README.md"] += f"\n离散格式: {scheme}；线性迎风与限制线性格式，原始场与日志保留。\n"
    for name, content in files.items():
        (path / name).write_text(content, encoding="utf8")
    return path


def create_channel(path: Path, *, length: float = 3, speed: float = 0.5, cells: int = 60) -> Path:
    """生成无流场求解的均匀活塞流通道，长度 m、速度 m/s。"""
    if length <= 0 or speed <= 0 or cells < 2:
        raise ValueError("通道参数无效")
    c = Room(length=length, width=1, height=1.5, opening=0.25, flow=0.03125)
    create_room(path, c, diffusivity=1e-9, iterations=10)
    p = Path(path)
    mesh = (
        "scale 1; vertices ((0 0 0) (%g 0 0) (%g 1 0) (0 1 0) (0 0 1) (%g 0 1) (%g 1 1) (0 1 1)); blocks (hex (0 1 2 3 4 5 6 7) (%d 4 4) simpleGrading (1 1 1)); edges (); boundary (inlet {type patch; faces ((0 4 7 3));} outlet {type patch; faces ((1 2 6 5));} walls {type wall; faces ((0 1 5 4) (3 7 6 2) (0 3 2 1) (4 5 6 7));}); mergePatchPairs ();"  # noqa: UP031
        % (length, length, length, length, cells)
    )
    (p / "system/blockMeshDict").write_text(dictionary("blockMeshDict", mesh))
    schemes = p / "system/fvSchemes"
    schemes.write_text(
        schemes.read_text().replace(
            "div(phi,T) bounded Gauss limitedLinear 1;", "div(phi,T) Gauss linearUpwind grad(T);"
        )
    )
    (p / "0/U").write_text(
        _field(
            "U",
            "[0 1 -1 0 0 0 0]",
            f"({speed:g} 0 0)",
            f"type fixedValue; value uniform ({speed:g} 0 0);",
            "type zeroGradient;",
            "type slip;",
        )
    )
    (p / "README.md").write_text(
        f"# 均匀活塞流解析验证\n\nL={length} m，U={speed} m/s，层流给定均匀速度，D=1e-9 m²/s，忽略速度扩散；出口空气龄应为 L/U。字典独立编写。\n"
    )
    return p


def _submit_script(name: str, path: Path, script: str) -> None:
    """用用户级任务和案例锁启动外部命令；可配置命令包装器。"""
    import os
    import re
    import shlex
    import subprocess

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,50}", name):
        raise ValueError("任务名无效")
    path = Path(path).resolve(strict=True)
    if not path.is_dir() or not path.is_relative_to(case_root()):
        raise ValueError("案例目录须位于专用 CFD 目录")
    prefix = shlex.split(os.environ.get("ORV_FOAM_CMD", ""))
    commands = (
        "blockMesh",
        "checkMesh",
        "simpleFoam",
        "foamListTimes",
        "scalarTransportFoam",
        "foamToVTK",
    )
    definitions = "\n".join(
        f'{command}() {{ command {shlex.join([*prefix, command])} "$@"; }}' for command in commands
    )
    subprocess.run(
        [
            "systemd-run",
            "--user",
            "--collect",
            f"--unit=openresivent-cfd-{name}",
            f"--working-directory={path}",
            "flock",
            "--nonblock",
            str(path / ".openresivent.lock"),
            "bash",
            "-c",
            definitions + "\n" + script,
        ],
        check=True,
    )


def submit_channel(name: str, path: Path) -> None:
    """提交给定均匀速度的通道标量计算。"""
    script = 'set -e; blockMesh > log.blockMesh 2>&1; checkMesh > log.checkMesh 2>&1; grep -q "Mesh OK" log.checkMesh; cp system/controlDict.age system/controlDict; scalarTransportFoam > log.scalar 2>&1; foamToVTK -latestTime > log.vtk 2>&1'
    _submit_script(name, path, script)


def submit(name: str, path: Path) -> None:
    """通过用户级任务提交已生成案例；以案例锁防止重复运行。"""
    script = 'set -e; blockMesh > log.blockMesh 2>&1; checkMesh > log.checkMesh 2>&1; grep -q "Mesh OK" log.checkMesh; simpleFoam > log.simpleFoam 2>&1; last=$(foamListTimes -latestTime); cp "$last/U" "$last/phi" 0/; cp system/controlDict.age system/controlDict; if [ -f 0/T.thermal ]; then cp 0/T 0/T.age; cp 0/T.thermal 0/T; cp constant/fvOptions constant/fvOptions.age; cp constant/fvOptions.thermal constant/fvOptions; scalarTransportFoam > log.thermal 2>&1; mv 10000 thermal-results; cp 0/T.age 0/T; cp constant/fvOptions.age constant/fvOptions; fi; scalarTransportFoam > log.scalar 2>&1; foamToVTK -latestTime > log.vtk 2>&1'
    _submit_script(name, path, script)


def from_network(
    flows: list[dict], inlet_index: int, outlet_index: int, *, tolerance: float = 1e-4
) -> float:
    """M2 路径质量流结果 → 平衡的入口上游体积流量 m³/s；不平衡拒绝。"""
    a, b = flows[inlet_index], flows[outlet_index]
    ma, mb = abs(a["mass_flow"]), abs(b["mass_flow"])
    if min(ma, mb) <= 0 or not 0 <= tolerance < 1 or abs(ma - mb) / max(ma, mb) > tolerance:
        raise ValueError("M2 边界质量流量不平衡")
    qa, qb = abs(a["volume_flow"]), abs(b["volume_flow"])
    if min(qa, qb) <= 0 or abs(qa - qb) / max(qa, qb) > tolerance:
        raise ValueError("不可压缩 CFD 要求入口和出口体积流量平衡；非等温网络需先定义参考密度")
    return qa


def oscillatory_uncertainty(efficiencies: list[float]) -> dict:
    """三网格效率（粗到细）→ 半极差及相对细网格无量纲不确定度。"""
    if len(efficiencies) != 3 or not all(math.isfinite(x) and 0 < x <= 1 for x in efficiencies):
        raise ValueError("三网格效率无效")
    half = (max(efficiencies) - min(efficiencies)) / 2
    return {"absolute": half, "relative_fine": half / efficiencies[-1]}


def gci(values: list[float], ratio: float) -> dict:
    """粗、中、细三网格解及统一加密比 → Roache GCI，非单调序列拒绝。"""
    if len(values) != 3 or ratio <= 1 or not all(math.isfinite(v) for v in values):
        raise ValueError("网格数据无效")
    coarse, medium, fine = values
    e21 = medium - fine
    e32 = coarse - medium
    if e21 == 0 or e21 * e32 <= 0 or fine == 0:
        raise ValueError("网格误差不满足单调收敛")
    order = math.log(abs(e32 / e21)) / math.log(ratio)
    if order <= 0:
        raise ValueError("观测阶数非正")
    return {
        "order": order,
        "gci_fine": 1.25 * abs(e21 / fine) / (ratio**order - 1),
        "extrapolated": fine + (fine - medium) / (ratio**order - 1),
    }
