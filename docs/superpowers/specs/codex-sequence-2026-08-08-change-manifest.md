<!-- codex-sequence-2026-08-08:begin -->
# Vizzer 0.2 lifecycle, relations, priority, activity, progress, and planning inventory

Exact SHA-256 inventory of the 36 upstream implementation, documentation, test, and generated
golden files changed for the IllTool Vizzer extension. This manifest excludes itself because a
self-hash cannot be stable.

| SHA-256 | Path |
|---|---|
| `4b21cde206e59e74375a23f5302b9f1eb04e857ee9e3a681383a36627b178b8f` | `README.md` |
| `e478e95803335e95e6053663916adf84d40c28699e489902c330f7880f422a04` | `docs/superpowers/specs/2026-08-06-vizzer-portable-spec-views-design.md` |
| `3f4fa59f5753924fe1242bdab696220072d016669396bee4acb81f79b9abda32` | `pyproject.toml` |
| `ba398b31a43869e10ce42a58485a54dc6be5640ed5067d230fea11e52004d15a` | `src/vizzer/__init__.py` |
| `e75a9c3ad93eed7f51c2d07db6bbe48c06df6b2628db2b21f2abb26c949ab9cd` | `src/vizzer/activity.py` |
| `3da19fea045925d900cc0dec112ad086a55e29671f7abfa402f58ab9545ee703` | `src/vizzer/adapters/__init__.py` |
| `01427628a8b98744fc8b3919a0f9b28d6f72da73348e54546906c2b1ce5e4116` | `src/vizzer/adapters/spec_tree.py` |
| `96b72e14fc54a29c9b0d65c66970bc7158e90681cbcddb37cf23ad15f12b45c5` | `src/vizzer/cli.py` |
| `4965c1a5dc5a02b3a89490c231ff52b6fc4ee3947ab91c524cd3144be3babc02` | `src/vizzer/config.py` |
| `cda178c4e7181c80ffdee8a4f4cd104eae12771bb5770d291e4ce7e34009bfe1` | `src/vizzer/install.py` |
| `103e1f1c2521c75a4545952dd4623768e09790fb8060b9e8759a6ff232e6eee5` | `src/vizzer/model.py` |
| `86e0f044c0c979fede529fdaee8b48f8142171deea084067b1e90d1d8bf864d4` | `src/vizzer/planning.py` |
| `0178e785d644e5e173c80b01cd6aa00ab0c9914f0c0c2307c7a47bbbcd8ab57c` | `src/vizzer/priority.py` |
| `ea3d7be10562a3db08edff9cb293a504a74490de6d460ae529c0f8c4731651de` | `src/vizzer/progress_history.py` |
| `0e55a59c256aa01c363b431dd5be1d239db8080ff2c90cd76a5e63bf6fe200c4` | `src/vizzer/reconcile.py` |
| `b0898e41f8f14c532a26da83fa2b9468e136579d7f4959c7dbef4889e6d57535` | `src/vizzer/render/common.py` |
| `44321d07d6d0e0b4ec48b3a2b8df19ee144d7c9584dc932c4c3284a0001bd612` | `src/vizzer/render/constellation.py` |
| `ef785554d2460b24bea40aba86cfd6b0d511d7c1eb705ebda2062947598dddd7` | `src/vizzer/render/constellation_template.html` |
| `94621f5cf1680752f496e8e9ff97b48f255ab1619a2500047062e13d5f541e30` | `src/vizzer/render/dashboard.py` |
| `3a114cd2f891237b4195b66767959fea4214c67268014327b0b4b84ef78c5f99` | `tests/golden/mixed/constellation.html` |
| `32332ce731dd3b60e8dfaa9086b82bae89f8664e26fb66a957bab8583572c14f` | `tests/golden/mixed/dashboard.md` |
| `6425d4179907cdb9fb734c197ad78b8513f3f99591d07683d2eff09f1e44a8ba` | `tests/golden/mixed/vizzer-graph.json` |
| `5e7682aef679966f22b803f851f7c592244ec280f2f2089c1ec404c5aaf47cfe` | `tests/test_activity.py` |
| `d3d922867cebe1c1840d9f05a3b11f53182151cc96a06a3f87cc8f5839ad07f1` | `tests/test_cli.py` |
| `2923c669635a6d9bbd2816365a736a82b3153d2936a84c5dad989b0f7d7bd863` | `tests/test_config.py` |
| `0bd8a2a8e076535e1bb3f6348e598c7cff0cd4af0cb42396b52276cd187f7bd1` | `tests/test_install.py` |
| `6351ac6fe02671aaf1581e4fb8c19e0cd9e15468cc7ac28a1a5970defe24318c` | `tests/test_model.py` |
| `bea1dfeb87263f8cdb1573504f4ad62bfac06029ec55c298d62e219132dfab45` | `tests/test_planning.py` |
| `8ffc6c24a177ac9b287fb53e3e4ab86ec1a7653729a7bf271ce539394ddb0cab` | `tests/test_planning_cli.py` |
| `c9ea3fab14897d0e17aa2c0d80a98d134e294001f1269c6e3ef46fdc9b2c4598` | `tests/test_planning_http.py` |
| `c340c7c2f85a17c308a30c302a03ef9a42ad3a18f9e787332533e40b2fb98616` | `tests/test_priority.py` |
| `53b3b617a35cf52d2391f6f326e8e5ee0d99a221c16852d0b00276af8b78ef69` | `tests/test_progress_history.py` |
| `f89378c061dba81e7e78f17449c6aab9387ee47ba68f83e2224120b669b628b7` | `tests/test_reconcile.py` |
| `ba30911345d59bc51f13148ee378b89edd700757df68f487fad3ad0364486e43` | `tests/test_render_constellation.py` |
| `e4800f7a7be8f61fd31d059652f8f2f96746135363faa19703d85e75051e8e6d` | `tests/test_render_dashboard.py` |
| `3df2a75f9e29834cb191333d289d777d0eba18d364d5c5698d0b84d3fee7c30f` | `tests/test_spec_tree.py` |

Verification: `183 passed`; generated constellation JavaScript parses with Node; elapsed time alone
does not stale the generated graph; `git diff --check` is clean. Source base:
`bc7ab060f0e3162ef2a651a0a61b371aca7e649f`.

<!-- codex-sequence-2026-08-08:end -->
