// Real SF Symbol outlines — copied exactly from Vizzer's generated catalog.
// Do not hand-edit the outline data; integration helpers live below the block.
//
// Regenerate with:
//   swift scripts/dev/export-sf-symbol-canvas-paths.swift eyeglasses checkmark.square \
//     questionmark arrow.up.right ladybug exclamationmark.triangle arrow.up \
//     list.dash.header.rectangle chevron.down xmark.circle \
//     checkmark parkingsign lightbulb document \
//     arrow.trianglehead.branch
//   swift scripts/dev/verify-sf-symbol-canvas-paths.swift <exported.json>
//
// These are the system glyphs themselves (NSImage(systemSymbolName:) -> vector
// outline), not hand-drawn approximations, and they ship as vectors so the page
// rasterizes them once at final size on every device-pixel ratio. The verify
// script reports mask IoU against the live system symbol; the committed data
// scored 0.99 / 0.95 / 0.99 (checkmark.square / eyeglasses / questionmark),
// 0.9652 / 0.9548 / 0.9926 (arrow.up.right / ladybug / exclamationmark.triangle),
// and 0.9917 / 0.9833 (list.dash.header.rectangle / chevron.down — iteration
// 2.8 chip-table trigger and More chevron, verified 2026-08-15), and 0.9649
// (xmark.circle — the blocked chip, verified 2026-08-15; the OUTLINE was
// chosen over xmark.circle.fill, which also rasterizes at IoU 0.9861, because
// the filled-disc treatment already means "status marker" in this row).
//
// FILL RULE IS PER SYMBOL, not global. Even-odd is correct for a single
// outline or a nested counter (a bowl inside a rim), which is every entry
// registered before 2026-08-17. It is WRONG for a glyph assembled from
// OVERLAPPING subpaths: arrow.trianglehead.branch lays its arrowheads over
// their stems, and even-odd punches each overlap into a hole — it scored IoU
// 0.3134 that way, and 0.9862 under nonzero (verified 2026-08-17; chevron.down
// still scores its documented 0.9833 under even-odd, so nothing regressed).
// Three different branch symbols scored an identical 0.3134, which is what
// showed the rule and not the glyph was at fault. Entries carry `fillRule`
// only when they need nonzero; drawSymbol and symbolMarkup default to evenodd.
//
// "arrow.up.baseline" is the one COMPOSED entry: SF Symbols has no
// arrow-up-from-line glyph (NSImage returns nil for arrow.up.from.line), so the
// owner's "up arrow with a baseline" is the real `arrow.up` outline (IoU 0.9622
// against the system symbol) scaled to the top 78% of the box plus a flat
// baseline bar across the bottom 12%. Regenerate via the gen script recorded in
// the symbol-iteration-two story stub; never hand-edit the numbers.
export const SYMBOL_OUTLINES = {
  "checkmark.square": {aspect: 0.9994, d: 'M0.1704,1.0000L0.8290,1.0000C0.9429,1.0000 0.9994,0.9432 0.9994,0.8314L0.9994,0.1687C0.9994,0.0568 0.9429,0.0000 0.8290,0.0000L0.1704,0.0000C0.0571,0.0000 0.0000,0.0566 0.0000,0.1687L0.0000,0.8314C0.0000,0.9434 0.0571,1.0000 0.1704,1.0000ZM0.1718,0.9121C0.1175,0.9121 0.0873,0.8831 0.0873,0.8271L0.0873,0.1729C0.0873,0.1163 0.1175,0.0879 0.1718,0.0879L0.8276,0.0879C0.8815,0.0879 0.9121,0.1163 0.9121,0.1729L0.9121,0.8271C0.9121,0.8831 0.8815,0.9121 0.8276,0.9121ZM0.4408,0.7578C0.4589,0.7578 0.4740,0.7492 0.4845,0.7326L0.7325,0.3421C0.7390,0.3314 0.7454,0.3192 0.7454,0.3072C0.7454,0.2830 0.7242,0.2669 0.7013,0.2669C0.6872,0.2669 0.6738,0.2756 0.6639,0.2918L0.4384,0.6529L0.3314,0.5147C0.3187,0.4974 0.3061,0.4925 0.2913,0.4925C0.2679,0.4925 0.2495,0.5117 0.2495,0.5360C0.2495,0.5477 0.2544,0.5593 0.2617,0.5697L0.3942,0.7326C0.4082,0.7499 0.4225,0.7578 0.4408,0.7578Z'},
  "eyeglasses": {aspect: 2.5301, d: 'M0.2589,0.3952C0.3678,0.3952 0.4563,0.3068 0.4563,0.1975C0.4563,0.0884 0.3678,0.0000 0.2589,0.0000C0.1495,0.0000 0.0609,0.0884 0.0609,0.1975C0.0609,0.3068 0.1495,0.3952 0.2589,0.3952ZM0.2589,0.3420C0.1792,0.3420 0.1143,0.2775 0.1143,0.1975C0.1143,0.1178 0.1792,0.0533 0.2589,0.0533C0.3382,0.0533 0.4030,0.1181 0.4030,0.1975C0.4030,0.2772 0.3382,0.3420 0.2589,0.3420ZM0.7415,0.3952C0.8505,0.3952 0.9394,0.3068 0.9394,0.1975C0.9394,0.0884 0.8505,0.0000 0.7415,0.0000C0.6322,0.0000 0.5437,0.0884 0.5437,0.1975C0.5437,0.3068 0.6322,0.3952 0.7415,0.3952ZM0.7415,0.3420C0.6618,0.3420 0.5970,0.2772 0.5970,0.1975C0.5970,0.1181 0.6618,0.0533 0.7415,0.0533C0.8212,0.0533 0.8857,0.1178 0.8857,0.1975C0.8857,0.2775 0.8212,0.3420 0.7415,0.3420ZM0.0817,0.1583L0.0238,0.1583C0.0083,0.1583 0.0000,0.1666 0.0000,0.1823L0.0000,0.1952C0.0000,0.2109 0.0083,0.2194 0.0238,0.2194L0.0817,0.2194ZM0.9183,0.2194L0.9762,0.2194C0.9921,0.2194 1.0000,0.2109 1.0000,0.1952L1.0000,0.1823C1.0000,0.1666 0.9921,0.1583 0.9762,0.1583L0.9183,0.1583ZM0.4406,0.2088C0.4569,0.1992 0.4790,0.1941 0.5002,0.1941C0.5211,0.1941 0.5432,0.1992 0.5594,0.2088L0.5594,0.1516C0.5415,0.1430 0.5180,0.1397 0.5002,0.1397C0.4823,0.1397 0.4588,0.1430 0.4406,0.1516Z'},
  "questionmark": {aspect: 0.5705, d: 'M0.2599,0.7122C0.2962,0.7122 0.3132,0.6873 0.3132,0.6537C0.3132,0.6477 0.3132,0.6418 0.3132,0.6358C0.3143,0.5668 0.3392,0.5376 0.4232,0.4803C0.5133,0.4190 0.5705,0.3486 0.5705,0.2478C0.5705,0.0899 0.4426,0.0000 0.2830,0.0000C0.1645,0.0000 0.0605,0.0560 0.0154,0.1577C0.0047,0.1816 0.0000,0.2061 0.0000,0.2263C0.0000,0.2561 0.0174,0.2769 0.0493,0.2769C0.0756,0.2769 0.0940,0.2610 0.1015,0.2355C0.1287,0.1358 0.1948,0.0980 0.2796,0.0980C0.3817,0.0980 0.4616,0.1556 0.4616,0.2473C0.4616,0.3225 0.4151,0.3637 0.3479,0.4111C0.2652,0.4689 0.2050,0.5296 0.2050,0.6224C0.2050,0.6335 0.2050,0.6443 0.2050,0.6548C0.2050,0.6890 0.2236,0.7122 0.2599,0.7122ZM0.2598,1.0000C0.3017,1.0000 0.3346,0.9658 0.3346,0.9252C0.3346,0.8834 0.3017,0.8505 0.2598,0.8505C0.2191,0.8505 0.1856,0.8834 0.1856,0.9252C0.1856,0.9658 0.2191,1.0000 0.2598,1.0000Z'},
  "arrow.up.right": {aspect: 1.0024, d: 'M0.0192,0.9793C0.0439,1.0032 0.0785,1.0043 0.1043,0.9793L0.7906,0.2930L0.9292,0.1446C0.9521,0.1219 0.9520,0.0910 0.9295,0.0691C0.9072,0.0468 0.8764,0.0467 0.8535,0.0693L0.7051,0.2068L0.0188,0.8938C-0.0068,0.9193 -0.0059,0.9540 0.0192,0.9793ZM0.8768,0.4984L0.8768,0.7487C0.8768,0.7804 0.9050,0.8097 0.9383,0.8097C0.9709,0.8097 1.0000,0.7827 1.0000,0.7459L0.9988,0.0652C0.9988,0.0272 0.9741,0.0000 0.9336,0.0000L0.2528,0.0000C0.2153,0.0000 0.1899,0.0286 0.1899,0.0615C0.1899,0.0938 0.2183,0.1213 0.2507,0.1213L0.4860,0.1213L0.8927,0.1080Z'},
  "ladybug": {aspect: 0.9648, d: 'M0.4826,1.0000C0.7069,1.0000 0.8562,0.8466 0.8562,0.6153C0.8562,0.4875 0.8001,0.3573 0.7097,0.2780C0.7088,0.1598 0.6189,0.0886 0.4826,0.0886C0.3454,0.0886 0.2561,0.1602 0.2551,0.2780C0.1650,0.3577 0.1086,0.4860 0.1086,0.6153C0.1086,0.8466 0.2582,1.0000 0.4826,1.0000ZM0.4826,0.3791C0.5573,0.3791 0.6318,0.3648 0.6808,0.3430C0.7332,0.3978 0.7899,0.4946 0.7899,0.6153C0.7899,0.8061 0.6668,0.9333 0.4826,0.9333C0.2980,0.9333 0.1753,0.8061 0.1753,0.6153C0.1753,0.4948 0.2308,0.3990 0.2843,0.3430C0.3330,0.3647 0.4075,0.3791 0.4826,0.3791ZM0.4529,0.9523L0.5087,0.9523L0.5087,0.4594C0.5087,0.4440 0.4962,0.4314 0.4807,0.4314C0.4654,0.4314 0.4529,0.4440 0.4529,0.4594ZM0.3464,0.5280C0.3761,0.5280 0.4000,0.5035 0.4000,0.4742C0.4000,0.4449 0.3762,0.4205 0.3464,0.4205C0.3171,0.4205 0.2932,0.4449 0.2932,0.4742C0.2932,0.5035 0.3171,0.5280 0.3464,0.5280ZM0.2957,0.6970C0.3300,0.6970 0.3582,0.6688 0.3582,0.6340C0.3582,0.5998 0.3300,0.5717 0.2957,0.5717C0.2611,0.5717 0.2329,0.5998 0.2329,0.6340C0.2329,0.6688 0.2611,0.6970 0.2957,0.6970ZM0.3464,0.8421C0.3741,0.8421 0.3960,0.8202 0.3960,0.7929C0.3960,0.7652 0.3741,0.7429 0.3464,0.7429C0.3191,0.7429 0.2973,0.7652 0.2973,0.7929C0.2973,0.8202 0.3191,0.8421 0.3464,0.8421ZM0.6183,0.5280C0.6476,0.5280 0.6715,0.5035 0.6715,0.4742C0.6715,0.4449 0.6476,0.4205 0.6183,0.4205C0.5885,0.4205 0.5648,0.4449 0.5648,0.4742C0.5648,0.5035 0.5887,0.5280 0.6183,0.5280ZM0.6691,0.6970C0.7036,0.6970 0.7318,0.6688 0.7318,0.6340C0.7318,0.5998 0.7036,0.5717 0.6691,0.5717C0.6348,0.5717 0.6067,0.5998 0.6067,0.6340C0.6067,0.6688 0.6348,0.6970 0.6691,0.6970ZM0.6183,0.8421C0.6456,0.8421 0.6680,0.8202 0.6680,0.7929C0.6680,0.7652 0.6456,0.7429 0.6183,0.7429C0.5911,0.7429 0.5688,0.7652 0.5688,0.7929C0.5688,0.8202 0.5911,0.8421 0.6183,0.8421ZM0.2950,0.0612L0.3237,0.0719C0.3424,0.0780 0.3497,0.0878 0.3461,0.1034L0.3412,0.1246L0.4037,0.1242L0.4064,0.1024C0.4113,0.0612 0.3919,0.0309 0.3501,0.0158L0.3160,0.0022C0.2740,-0.0122 0.2537,0.0493 0.2950,0.0612ZM0.6698,0.0612C0.7111,0.0493 0.6906,-0.0122 0.6489,0.0022L0.6148,0.0158C0.5728,0.0309 0.5535,0.0612 0.5584,0.1024L0.5616,0.1242L0.6236,0.1246L0.6187,0.1034C0.6156,0.0878 0.6224,0.0780 0.6411,0.0719ZM0.2171,0.3568L0.1378,0.2897C0.1221,0.2762 0.1017,0.2750 0.0888,0.2909C0.0759,0.3059 0.0806,0.3268 0.0961,0.3398L0.1763,0.4073ZM0.1396,0.5580L0.0350,0.5583C0.0139,0.5583 0.0000,0.5713 0.0000,0.5910C0.0000,0.6105 0.0139,0.6234 0.0351,0.6234L0.1396,0.6229ZM0.1738,0.8070L0.0945,0.8737C0.0791,0.8868 0.0743,0.9072 0.0874,0.9226C0.1003,0.9387 0.1205,0.9368 0.1364,0.9233L0.2151,0.8573ZM0.7473,0.3570L0.7884,0.4075L0.8687,0.3398C0.8841,0.3268 0.8893,0.3059 0.8765,0.2909C0.8634,0.2750 0.8427,0.2762 0.8269,0.2897ZM0.8254,0.5580L0.8254,0.6229L0.9298,0.6234C0.9509,0.6234 0.9648,0.6105 0.9648,0.5910C0.9648,0.5713 0.9509,0.5583 0.9299,0.5583ZM0.7906,0.8068L0.7495,0.8568L0.8283,0.9233C0.8443,0.9368 0.8645,0.9387 0.8774,0.9226C0.8905,0.9072 0.8858,0.8868 0.8702,0.8737Z'},
  "exclamationmark.triangle": {aspect: 1.1033, d: 'M0.1302,0.9064L0.8698,0.9064C0.9508,0.9064 1.0000,0.8498 1.0000,0.7767C1.0000,0.7545 0.9935,0.7311 0.9813,0.7097L0.6111,0.0650C0.5864,0.0220 0.5438,0.0000 0.5001,0.0000C0.4562,0.0000 0.4132,0.0220 0.3889,0.0650L0.0187,0.7097C0.0060,0.7316 0.0000,0.7545 0.0000,0.7767C0.0000,0.8498 0.0492,0.9064 0.1302,0.9064ZM0.1308,0.8312C0.0976,0.8312 0.0769,0.8052 0.0769,0.7766C0.0769,0.7671 0.0793,0.7558 0.0845,0.7462L0.4541,0.1012C0.4640,0.0838 0.4822,0.0758 0.5001,0.0758C0.5173,0.0758 0.5350,0.0838 0.5455,0.1012L0.9150,0.7468C0.9202,0.7563 0.9226,0.7671 0.9226,0.7766C0.9226,0.8052 0.9020,0.8312 0.8687,0.8312ZM0.5001,0.5845C0.5227,0.5845 0.5359,0.5716 0.5364,0.5466L0.5433,0.2950C0.5438,0.2710 0.5246,0.2526 0.4995,0.2526C0.4734,0.2526 0.4557,0.2705 0.4562,0.2944L0.4623,0.5466C0.4628,0.5711 0.4758,0.5845 0.5001,0.5845ZM0.5001,0.7396C0.5276,0.7396 0.5511,0.7179 0.5511,0.6900C0.5511,0.6620 0.5281,0.6404 0.5001,0.6404C0.4719,0.6404 0.4484,0.6625 0.4484,0.6900C0.4484,0.7174 0.4724,0.7396 0.5001,0.7396Z'},
  "list.dash.header.rectangle": {aspect: 1.2800, d: 'M0.1331,0.7812L0.8669,0.7812C0.9558,0.7812 1.0000,0.7368 1.0000,0.6495L1.0000,0.1318C1.0000,0.0444 0.9558,0.0000 0.8669,0.0000L0.1331,0.0000C0.0446,0.0000 0.0000,0.0442 0.0000,0.1318L0.0000,0.6495C0.0000,0.7370 0.0446,0.7812 0.1331,0.7812ZM0.1342,0.7126C0.0918,0.7126 0.0682,0.6899 0.0682,0.6461L0.0682,0.1351C0.0682,0.0909 0.0918,0.0686 0.1342,0.0686L0.8658,0.0686C0.9078,0.0686 0.9318,0.0909 0.9318,0.1351L0.9318,0.6461C0.9318,0.6899 0.9078,0.7126 0.8658,0.7126ZM0.2119,0.2417L0.2632,0.2417C0.2812,0.2417 0.2961,0.2269 0.2961,0.2094C0.2961,0.1911 0.2811,0.1767 0.2632,0.1767L0.2119,0.1767C0.1940,0.1767 0.1795,0.1911 0.1795,0.2094C0.1795,0.2268 0.1944,0.2417 0.2119,0.2417ZM0.3823,0.2359L0.7933,0.2359C0.8083,0.2359 0.8197,0.2240 0.8197,0.2094C0.8197,0.1945 0.8082,0.1830 0.7933,0.1830L0.3823,0.1830C0.3674,0.1830 0.3560,0.1945 0.3560,0.2094C0.3560,0.2240 0.3673,0.2359 0.3823,0.2359ZM0.2119,0.3831L0.2632,0.3831C0.2811,0.3831 0.2961,0.3688 0.2961,0.3509C0.2961,0.3330 0.2815,0.3182 0.2632,0.3182L0.2119,0.3182C0.1940,0.3182 0.1795,0.3330 0.1795,0.3509C0.1795,0.3688 0.1940,0.3831 0.2119,0.3831ZM0.3823,0.3774L0.7933,0.3774C0.8083,0.3774 0.8197,0.3658 0.8197,0.3509C0.8197,0.3358 0.8083,0.3239 0.7933,0.3239L0.3823,0.3239C0.3678,0.3239 0.3560,0.3354 0.3560,0.3509C0.3560,0.3654 0.3673,0.3774 0.3823,0.3774Z'},
  "chevron.down": {aspect: 1.7766, d: 'M0.5002,0.5629C0.5148,0.5629 0.5289,0.5573 0.5390,0.5460L0.9845,0.0899C0.9942,0.0803 1.0000,0.0677 1.0000,0.0530C1.0000,0.0230 0.9775,0.0000 0.9476,0.0000C0.9335,0.0000 0.9195,0.0061 0.9098,0.0152L0.4692,0.4653L0.5308,0.4653L0.0901,0.0152C0.0805,0.0061 0.0676,0.0000 0.0530,0.0000C0.0230,0.0000 0.0000,0.0230 0.0000,0.0530C0.0000,0.0677 0.0059,0.0803 0.0156,0.0901L0.4616,0.5461C0.4721,0.5574 0.4851,0.5629 0.5002,0.5629Z'},
  "xmark.circle": {aspect: 1.0006, d: 'M0.4997,0.9994C0.7758,0.9994 1.0000,0.7758 1.0000,0.4997C1.0000,0.2235 0.7758,0.0000 0.4997,0.0000C0.2242,0.0000 0.0000,0.2235 0.0000,0.4997C0.0000,0.7758 0.2242,0.9994 0.4997,0.9994ZM0.4997,0.9164C0.2694,0.9164 0.0834,0.7300 0.0834,0.4997C0.0834,0.2694 0.2694,0.0830 0.4997,0.0830C0.7301,0.0830 0.9165,0.2694 0.9165,0.4997C0.9165,0.7300 0.7301,0.9164 0.4997,0.9164ZM0.3602,0.6950L0.6946,0.3606C0.7020,0.3532 0.7063,0.3439 0.7063,0.3333C0.7063,0.3113 0.6888,0.2943 0.6671,0.2943C0.6561,0.2943 0.6472,0.2980 0.6398,0.3061L0.3047,0.6395C0.2974,0.6474 0.2931,0.6562 0.2931,0.6673C0.2931,0.6893 0.3107,0.7068 0.3323,0.7068C0.3440,0.7068 0.3533,0.7026 0.3602,0.6950ZM0.6387,0.6950C0.6462,0.7026 0.6555,0.7068 0.6671,0.7068C0.6888,0.7068 0.7063,0.6893 0.7063,0.6673C0.7063,0.6562 0.7020,0.6474 0.6946,0.6395L0.3597,0.3061C0.3523,0.2980 0.3434,0.2943 0.3323,0.2943C0.3107,0.2943 0.2931,0.3113 0.2931,0.3333C0.2931,0.3439 0.2974,0.3532 0.3047,0.3606Z'},
  "checkmark": {aspect: 1.0083, d: 'M0.3786,0.9918C0.4034,0.9918 0.4230,0.9810 0.4370,0.9594L0.9853,0.0964C0.9962,0.0796 1.0000,0.0662 1.0000,0.0529C1.0000,0.0215 0.9791,0.0000 0.9471,0.0000C0.9241,0.0000 0.9111,0.0078 0.8971,0.0301L0.3760,0.8603L0.1056,0.5061C0.0910,0.4862 0.0767,0.4778 0.0555,0.4778C0.0232,0.4778 0.0000,0.5004 0.0000,0.5326C0.0000,0.5461 0.0057,0.5608 0.0168,0.5750L0.3178,0.9582C0.3358,0.9812 0.3536,0.9918 0.3786,0.9918Z'},
  "parkingsign": {aspect: 0.6683, d: 'M0.0653,1.0000C0.1046,1.0000 0.1305,0.9729 0.1305,0.9329L0.1305,0.6348L0.3452,0.6348C0.5359,0.6348 0.6683,0.5042 0.6683,0.3173C0.6683,0.1294 0.5364,0.0000 0.3457,0.0000L0.0653,0.0000C0.0260,0.0000 0.0000,0.0266 0.0000,0.0671L0.0000,0.9329C0.0000,0.9736 0.0260,1.0000 0.0653,1.0000ZM0.1305,0.5150L0.1305,0.1196L0.3213,0.1196C0.4573,0.1196 0.5355,0.1914 0.5355,0.3173C0.5355,0.4425 0.4572,0.5150 0.3213,0.5150Z'},
  "lightbulb": {aspect: 0.5755, d: 'M0.0000,0.2649C0.0000,0.4300 0.0991,0.4705 0.1264,0.7572C0.1279,0.7728 0.1366,0.7826 0.1533,0.7826L0.4222,0.7826C0.4389,0.7826 0.4477,0.7728 0.4492,0.7572C0.4766,0.4705 0.5755,0.4300 0.5755,0.2649C0.5755,0.1164 0.4487,0.0000 0.2878,0.0000C0.1269,0.0000 0.0000,0.1164 0.0000,0.2649ZM0.0651,0.2649C0.0651,0.1489 0.1668,0.0650 0.2878,0.0650C0.4087,0.0650 0.5105,0.1489 0.5105,0.2649C0.5105,0.3881 0.4287,0.4173 0.3896,0.7179L0.1860,0.7179C0.1468,0.4173 0.0651,0.3881 0.0651,0.2649ZM0.1515,0.8756L0.4237,0.8756C0.4379,0.8756 0.4488,0.8644 0.4488,0.8505C0.4488,0.8363 0.4379,0.8255 0.4237,0.8255L0.1515,0.8255C0.1375,0.8255 0.1264,0.8363 0.1264,0.8505C0.1264,0.8644 0.1375,0.8756 0.1515,0.8756ZM0.2878,1.0000C0.3544,1.0000 0.4101,0.9677 0.4138,0.9182L0.1614,0.9182C0.1646,0.9677 0.2206,1.0000 0.2878,1.0000Z'},
  "document": {aspect: 0.7847, d: 'M0.1444,1.0000L0.6398,1.0000C0.7362,1.0000 0.7847,0.9509 0.7847,0.8536L0.7847,0.4300C0.7847,0.3704 0.7778,0.3443 0.7405,0.3060L0.4831,0.0442C0.4479,0.0079 0.4187,0.0000 0.3660,0.0000L0.1444,0.0000C0.0483,0.0000 0.0000,0.0491 0.0000,0.1463L0.0000,0.8536C0.0000,0.9514 0.0481,1.0000 0.1444,1.0000ZM0.1481,0.9250C0.0999,0.9250 0.0750,0.8991 0.0750,0.8524L0.0750,0.1475C0.0750,0.1015 0.0999,0.0750 0.1485,0.0750L0.3558,0.0750L0.3558,0.3460C0.3558,0.4046 0.3856,0.4338 0.4436,0.4338L0.7092,0.4338L0.7092,0.8524C0.7092,0.8991 0.6842,0.9250 0.6362,0.9250ZM0.4522,0.3632C0.4337,0.3632 0.4259,0.3554 0.4259,0.3370L0.4259,0.0894L0.6948,0.3632Z'},
  "arrow.trianglehead.branch": {aspect: 0.9835, fillRule: "nonzero", d: 'M0.1315,0.2568L0.2752,0.0583C0.2973,0.0278 0.2821,0.0040 0.2466,0.0034L0.0382,0.0000C0.0090,-0.0007 -0.0070,0.0204 0.0029,0.0489L0.0697,0.2453C0.0816,0.2801 0.1087,0.2873 0.1315,0.2568ZM0.4461,0.9542C0.4461,0.9798 0.4669,1.0000 0.4918,1.0000C0.5168,1.0000 0.5376,0.9798 0.5376,0.9542L0.5376,0.6425C0.5376,0.4074 0.4058,0.2050 0.1746,0.0788C0.1468,0.0631 0.1222,0.0781 0.1116,0.0992C0.1027,0.1194 0.1063,0.1448 0.1301,0.1586C0.3351,0.2701 0.4461,0.4431 0.4461,0.6425ZM0.8518,0.2568C0.8744,0.2873 0.9017,0.2801 0.9129,0.2453L0.9803,0.0489C0.9908,0.0204 0.9743,-0.0007 0.9453,0.0000L0.7367,0.0034C0.7010,0.0040 0.6858,0.0278 0.7079,0.0583ZM0.5376,0.9542L0.5376,0.6425C0.5376,0.4431 0.6485,0.2701 0.8536,0.1586C0.8774,0.1448 0.8810,0.1194 0.8721,0.0992C0.8615,0.0781 0.8370,0.0631 0.8092,0.0788C0.5778,0.2050 0.4461,0.4074 0.4461,0.6425L0.4461,0.9542C0.4461,0.9798 0.4669,1.0000 0.4918,1.0000C0.5168,1.0000 0.5376,0.9798 0.5376,0.9542Z'},
  "arrow.up.baseline": {aspect: 0.8020, d: 'M0.1239,0.3500C0.1335,0.3500 0.1433,0.3462 0.1497,0.3399L0.2438,0.2474L0.4005,0.0753L0.5582,0.2474L0.6525,0.3399C0.6588,0.3462 0.6684,0.3500 0.6782,0.3500C0.6986,0.3500 0.7138,0.3341 0.7138,0.3137C0.7138,0.3040 0.7103,0.2954 0.7025,0.2868L0.4284,0.0127C0.4206,0.0045 0.4112,0.0000 0.4011,0.0000C0.3909,0.0000 0.3814,0.0045 0.3736,0.0127L0.0997,0.2868C0.0919,0.2954 0.0882,0.3040 0.0882,0.3137C0.0882,0.3341 0.1034,0.3500 0.1239,0.3500ZM0.4011,0.7800C0.4224,0.7800 0.4380,0.7648 0.4380,0.7434L0.4380,0.2000L0.4334,0.0771C0.4334,0.0580 0.4203,0.0445 0.4011,0.0445C0.3818,0.0445 0.3685,0.0580 0.3685,0.0771L0.3640,0.2000L0.3640,0.7434C0.3640,0.7648 0.3795,0.7800 0.4011,0.7800ZM0.0000,0.8800L0.8020,0.8800L0.8020,1.0000L0.0000,1.0000Z'},
};

// Developer-object semantic symbols, generated by the same AppKit exporter as
// the canonical catalog above. These are presentation guesses only: portable
// object data never stores an Apple symbol name.
Object.assign(SYMBOL_OUTLINES,{
  "cloud": {aspect:1.5101607680881268,fillRule:"evenodd",d:'M0.2049,0.6622L0.7499,0.6622C0.8904,0.6622 1.0000,0.5559 1.0000,0.4192C1.0000,0.2817 0.8884,0.1776 0.7364,0.1777C0.6806,0.0675 0.5786,0.0000 0.4546,0.0000C0.2923,0.0000 0.1549,0.1257 0.1402,0.2927C0.0566,0.3167 0.0000,0.3872 0.0000,0.4759C0.0000,0.5791 0.0748,0.6622 0.2049,0.6622ZM0.2040,0.5948C0.1184,0.5948 0.0674,0.5484 0.0674,0.4782C0.0674,0.4179 0.1059,0.3746 0.1735,0.3565C0.1969,0.3506 0.2056,0.3400 0.2074,0.3152C0.2177,0.1736 0.3241,0.0673 0.4546,0.0673C0.5551,0.0673 0.6334,0.1234 0.6802,0.2198C0.6899,0.2404 0.7022,0.2472 0.7275,0.2472C0.8584,0.2472 0.9322,0.3264 0.9322,0.4212C0.9322,0.5184 0.8544,0.5948 0.7547,0.5948Z'},
  "cylinder": {aspect:0.8163687855721753,fillRule:"evenodd",d:'M0.4081,1.0000C0.6532,1.0000 0.8164,0.9071 0.8164,0.7760L0.8164,0.2016L0.7400,0.2016L0.7400,0.7760C0.7400,0.8645 0.6072,0.9286 0.4081,0.9286C0.2092,0.9286 0.0763,0.8645 0.0763,0.7760L0.0763,0.2016L0.0000,0.2016L0.0000,0.7760C0.0000,0.9071 0.1630,1.0000 0.4081,1.0000ZM0.4081,0.4036C0.6532,0.4036 0.8164,0.3216 0.8164,0.2016C0.8164,0.0821 0.6532,0.0000 0.4081,0.0000C0.1630,0.0000 0.0000,0.0821 0.0000,0.2016C0.0000,0.3216 0.1630,0.4036 0.4081,0.4036ZM0.4081,0.3319C0.2092,0.3319 0.0763,0.2785 0.0763,0.2016C0.0763,0.1221 0.2092,0.0668 0.4081,0.0668C0.6072,0.0668 0.7400,0.1221 0.7400,0.2016C0.7400,0.2785 0.6072,0.3319 0.4081,0.3319Z'},
  "lock": {aspect:0.6962861109974012,fillRule:"evenodd",d:'M0.1146,1.0000L0.5817,1.0000C0.6566,1.0000 0.6963,0.9594 0.6963,0.8786L0.6963,0.5275C0.6963,0.4473 0.6566,0.4066 0.5817,0.4066L0.1146,0.4066C0.0397,0.4066 0.0000,0.4473 0.0000,0.5275L0.0000,0.8786C0.0000,0.9594 0.0397,1.0000 0.1146,1.0000ZM0.1173,0.9233C0.0955,0.9233 0.0823,0.9096 0.0823,0.8843L0.0823,0.5220C0.0823,0.4967 0.0955,0.4833 0.1173,0.4833L0.5790,0.4833C0.6012,0.4833 0.6140,0.4967 0.6140,0.5220L0.6140,0.8843C0.6140,0.9096 0.6012,0.9233 0.5790,0.9233ZM0.0896,0.4458L0.1703,0.4458L0.1703,0.2738C0.1703,0.1448 0.2529,0.0767 0.3479,0.0767C0.4433,0.0767 0.5264,0.1448 0.5264,0.2738L0.5264,0.4458L0.6071,0.4458L0.6071,0.2848C0.6071,0.0925 0.4817,0.0000 0.3479,0.0000C0.2146,0.0000 0.0896,0.0925 0.0896,0.2848Z'},
  "rectangle.on.rectangle": {aspect:1.2275945065010396,fillRule:"evenodd",d:'M0.1262,0.6285L0.6756,0.6285C0.7590,0.6285 0.8017,0.5868 0.8017,0.5040L0.8017,0.1249C0.8017,0.0420 0.7590,0.0000 0.6756,0.0000L0.1262,0.0000C0.0419,0.0000 0.0000,0.0418 0.0000,0.1249L0.0000,0.5040C0.0000,0.5870 0.0419,0.6285 0.1262,0.6285ZM0.1272,0.5638C0.0870,0.5638 0.0646,0.5423 0.0646,0.5004L0.0646,0.1280C0.0646,0.0862 0.0870,0.0651 0.1272,0.0651L0.6745,0.0651C0.7140,0.0651 0.7367,0.0862 0.7367,0.1280L0.7367,0.5004C0.7367,0.5423 0.7140,0.5638 0.6745,0.5638ZM0.3249,0.8146L0.8738,0.8146C0.9577,0.8146 1.0000,0.7726 1.0000,0.6902L1.0000,0.3106C1.0000,0.2279 0.9577,0.1862 0.8738,0.1862L0.3249,0.1862C0.2405,0.1862 0.1987,0.2277 0.1987,0.3106L0.1987,0.6902C0.1987,0.7732 0.2405,0.8146 0.3249,0.8146ZM0.3259,0.7501C0.2857,0.7501 0.2633,0.7284 0.2633,0.6866L0.2633,0.3143C0.2633,0.2724 0.2857,0.2509 0.3259,0.2509L0.8728,0.2509C0.9126,0.2509 0.9354,0.2724 0.9354,0.3143L0.9354,0.6866C0.9354,0.7284 0.9126,0.7501 0.8728,0.7501Z'},
  "scribble.variable": {aspect:1.107654718834852,fillRule:"evenodd",d:'M0.0209,0.6066C0.0453,0.6313 0.0948,0.6376 0.1332,0.6027C0.1456,0.5917 0.1722,0.5634 0.2223,0.5128C0.4636,0.2688 0.6221,0.1083 0.6562,0.1393C0.6839,0.1635 0.6003,0.2809 0.5210,0.3904C0.3723,0.5970 0.2542,0.7410 0.3418,0.8286C0.4118,0.8985 0.5214,0.8279 0.6898,0.6803C0.7844,0.5966 0.8557,0.5295 0.8765,0.5507C0.8917,0.5657 0.8680,0.6058 0.8327,0.6667C0.7869,0.7451 0.7298,0.8294 0.7847,0.8837C0.8221,0.9216 0.8955,0.9049 0.9857,0.8167C1.0010,0.8014 1.0053,0.7833 0.9923,0.7704C0.9805,0.7586 0.9632,0.7601 0.9508,0.7726C0.8846,0.8363 0.8422,0.8568 0.8316,0.8452C0.8184,0.8331 0.8417,0.7915 0.8898,0.7070C0.9501,0.6002 0.9828,0.5332 0.9317,0.4835C0.8626,0.4164 0.7812,0.4880 0.6308,0.6203C0.4884,0.7456 0.4468,0.7655 0.4293,0.7481C0.4050,0.7238 0.4418,0.6801 0.6006,0.4582C0.7493,0.2504 0.8351,0.1210 0.7548,0.0429C0.6449,-0.0645 0.5038,0.0204 0.1161,0.4038C0.0647,0.4544 0.0365,0.4810 0.0252,0.4935C-0.0113,0.5334 -0.0040,0.5823 0.0209,0.6066Z'},
  "server.rack": {aspect:1.2800294689251983,fillRule:"evenodd",d:'M0.7826,0.2090C0.8120,0.2084 0.8362,0.1843 0.8362,0.1549C0.8362,0.1253 0.8120,0.1002 0.7826,0.1002C0.7537,0.1002 0.7284,0.1253 0.7284,0.1549C0.7284,0.1843 0.7537,0.2095 0.7826,0.2090ZM0.7826,0.4439C0.8120,0.4434 0.8362,0.4193 0.8362,0.3898C0.8362,0.3603 0.8120,0.3352 0.7826,0.3352C0.7537,0.3352 0.7284,0.3603 0.7284,0.3898C0.7284,0.4193 0.7537,0.4445 0.7826,0.4439ZM0.7826,0.6789C0.8120,0.6783 0.8362,0.6542 0.8362,0.6248C0.8362,0.5953 0.8120,0.5702 0.7826,0.5702C0.7537,0.5702 0.7284,0.5953 0.7284,0.6248C0.7284,0.6542 0.7537,0.6794 0.7826,0.6789ZM0.9634,0.3048L0.9634,0.2406L0.0380,0.2406L0.0380,0.3048ZM0.9634,0.5411L0.9634,0.4768L0.0380,0.4768L0.0380,0.5411ZM0.1331,0.7812L0.8669,0.7812C0.9558,0.7812 1.0000,0.7368 1.0000,0.6495L1.0000,0.1318C1.0000,0.0444 0.9558,0.0000 0.8669,0.0000L0.1331,0.0000C0.0446,0.0000 0.0000,0.0442 0.0000,0.1318L0.0000,0.6495C0.0000,0.7370 0.0446,0.7812 0.1331,0.7812ZM0.1342,0.7126C0.0918,0.7126 0.0682,0.6899 0.0682,0.6461L0.0682,0.1351C0.0682,0.0909 0.0918,0.0686 0.1342,0.0686L0.8658,0.0686C0.9078,0.0686 0.9318,0.0909 0.9318,0.1351L0.9318,0.6461C0.9318,0.6899 0.9078,0.7126 0.8658,0.7126Z'},
  "sparkles": {aspect:0.8114181251637671,fillRule:"evenodd",d:'M0.3807,0.2135C0.3864,0.2135 0.3896,0.2099 0.3906,0.2050C0.4035,0.1339 0.4026,0.1305 0.4786,0.1170C0.4840,0.1160 0.4876,0.1126 0.4876,0.1070C0.4876,0.1013 0.4840,0.0981 0.4786,0.0971C0.4026,0.0834 0.4035,0.0802 0.3906,0.0090C0.3896,0.0037 0.3864,0.0000 0.3807,0.0000C0.3754,0.0000 0.3723,0.0037 0.3712,0.0090C0.3579,0.0802 0.3592,0.0834 0.2831,0.0971C0.2777,0.0981 0.2742,0.1013 0.2742,0.1070C0.2742,0.1126 0.2777,0.1160 0.2831,0.1170C0.3592,0.1305 0.3579,0.1339 0.3712,0.2050C0.3723,0.2099 0.3754,0.2135 0.3807,0.2135ZM0.1691,0.5151C0.1770,0.5151 0.1825,0.5098 0.1836,0.5018C0.1994,0.3847 0.2032,0.3850 0.3243,0.3614C0.3318,0.3604 0.3377,0.3550 0.3377,0.3469C0.3377,0.3385 0.3318,0.3332 0.3243,0.3322C0.2032,0.3150 0.1989,0.3112 0.1836,0.1922C0.1825,0.1837 0.1770,0.1783 0.1691,0.1783C0.1607,0.1783 0.1553,0.1837 0.1542,0.1927C0.1398,0.3098 0.1334,0.3090 0.0134,0.3322C0.0060,0.3337 0.0000,0.3385 0.0000,0.3469C0.0000,0.3554 0.0060,0.3604 0.0153,0.3614C0.1343,0.3808 0.1398,0.3839 0.1542,0.5009C0.1553,0.5098 0.1607,0.5151 0.1691,0.5151ZM0.4663,1.0000C0.4775,1.0000 0.4861,0.9921 0.4880,0.9804C0.5191,0.7403 0.5531,0.7034 0.7905,0.6770C0.8028,0.6760 0.8114,0.6669 0.8114,0.6555C0.8114,0.6436 0.8028,0.6351 0.7905,0.6336C0.5531,0.6071 0.5191,0.5707 0.4880,0.3306C0.4861,0.3184 0.4775,0.3107 0.4663,0.3107C0.4548,0.3107 0.4461,0.3184 0.4447,0.3306C0.4132,0.5707 0.3791,0.6071 0.1417,0.6336C0.1294,0.6351 0.1212,0.6436 0.1212,0.6555C0.1212,0.6669 0.1294,0.6760 0.1417,0.6770C0.3784,0.7083 0.4115,0.7404 0.4447,0.9804C0.4461,0.9921 0.4548,1.0000 0.4663,1.0000Z'},
});

// Path2D is constructed lazily and cached: the assembled script also runs in the
// minimal DOM used by the startup smoke test, which has no Path2D at all.
const symbolPathCache = new Map();
function symbolOutline(name){
  if(symbolPathCache.has(name))return symbolPathCache.get(name);
  const entry=SYMBOL_OUTLINES[name];
  const path=(entry&&typeof Path2D!=='undefined')?new Path2D(entry.d):null;
  symbolPathCache.set(name,path);
  return path;
}
// The exporter normalizes each outline so its LONGER side is exactly 1, which
// leaves the shorter side at 1/aspect. Every consumer needs that pair, so it is
// derived in one place instead of being re-inferred (wrongly) per call site.
const symbolAspect = name => (SYMBOL_OUTLINES[name]||{}).aspect||1;
function symbolUnitBox(name){
  const aspect=symbolAspect(name);
  return aspect>=1?{w:1,h:1/aspect}:{w:aspect,h:1};
}
// Inline SVG for the legend, built from the SAME outline data the canvas fills,
// so the key can never drift into showing a different mark than the map.
function symbolMarkup(name,height=13){
  const entry=SYMBOL_OUTLINES[name];
  if(!entry)return '';
  const box=symbolUnitBox(name),width=height*(box.w/box.h);
  return `<svg class="symbolkeyglyph" width="${width.toFixed(1)}" height="${height}" `
    +`viewBox="0 0 ${box.w.toFixed(4)} ${box.h.toFixed(4)}" aria-hidden="true">`
    +`<path fill="currentColor" fill-rule="${entry.fillRule||'evenodd'}" d="${entry.d}"/></svg>`;
}
// Iteration 2.2 (owner): the separate bottom legend is gone — the FILTER
// CHIPS are the legend now (legendChipPlan in filters.js), each carrying its
// symbol at a larger size from the same outline data the canvas fills.
// Draw a symbol centred on (x,y) at the given height in CSS pixels.
//
// Crispness rule: the outline is filled once at final size — never scaled up
// from a cached raster — and both the origin and the size snap to whole DEVICE
// pixels so edges land on pixel boundaries at DPR 1 and DPR 2 alike. Snapping
// the size as well as the origin matters: a fractional size puts the opposite
// edge back between pixels no matter where the origin sits.
function drawSymbol(context,name,x,y,height,dpr){
  const entry=SYMBOL_OUTLINES[name],path=symbolOutline(name);
  if(!entry||!path)return;
  const device=Math.max(1,dpr||1),box=symbolUnitBox(name);
  const painted=Math.max(1,Math.round(height*device))/device;
  const scale=painted/box.h,width=box.w*scale;
  context.save();
  context.translate(Math.round((x-width/2)*device)/device,
                    Math.round((y-painted/2)*device)/device);
  context.scale(scale,scale);
  // The outlines carry their counters as overlapping subpaths; even-odd is what
  // punches the lens holes and the checkbox interior back out.
  context.fill(path,entry.fillRule||'evenodd');
  context.restore();
}
// ---- symbol assignment (owner notes 2026-08-15) ----
// Pure functions over the node payload so a DOM-less test can drive the
// status -> symbol mapping without a canvas. The canvas paints exactly what
// these return; a divergence would make the legend and the map lie.
//
// Serious-bug severity comes from a REAL priority-engine field, never a
// heuristic: `dt` is the defect ranking's `target_impact` component (how many
// release targets the bug's reach hits — the engine's own docs call reach
// severity). A bug-gap without defect data, or with zero target impact, stays
// an ordinary bug.
function bugSeverity(node){
  if((node||{}).g!=='buggap')return '';
  return (Number(node.dt)||0)>0?'serious':'bug';
}
// Extra marks above the node: "up next" (arrow on a baseline) for the ranked
// next-up recommendations, "in progress" (45-degree arrow) for building /
// in-flight stories. Both can apply at once; the caller lays them out.
function nodeStatusMarkers(node){
  const markers=[];
  if((node||{}).rec)markers.push('arrow.up.baseline');
  const status=(node||{}).st;
  if(status==='building'||status==='in-flight')markers.push('arrow.up.right');
  return markers;
}
// Iteration 2.1 (owner: "the arrow is in the circle, inverted"): status marks
// render as a filled disc with the glyph knocked out in the page background,
// the treatment the question badge established. This pure geometry seam fits
// the glyph's longer side to a fixed share of the disc so the canvas and any
// DOM-less test derive the identical inversion.
function statusMarkerGeometry(name,badgeRadius){
  const box=symbolUnitBox(name);
  const maxDimension=badgeRadius*2*.62;
  const glyphHeight=box.h>=box.w?maxDimension:maxDimension*(box.h/box.w);
  return {badgeRadius,glyphHeight,glyphWidth:glyphHeight*(box.w/box.h)};
}
// Legend twin of the inverted disc treatment, from the SAME outline data the
// canvas fills, so the key cannot drift from the map.
function invertedSymbolMarkup(name,height=13){
  const entry=SYMBOL_OUTLINES[name];
  if(!entry)return '';
  const radius=height/2;
  const geometry=statusMarkerGeometry(name,radius);
  const box=symbolUnitBox(name);
  const scale=geometry.glyphHeight/box.h;
  const offsetX=radius-geometry.glyphWidth/2,offsetY=radius-geometry.glyphHeight/2;
  return `<svg class="symbolkeyglyph" width="${height}" height="${height}" `
    +`viewBox="0 0 ${height} ${height}" aria-hidden="true">`
    +`<circle cx="${radius}" cy="${radius}" r="${radius}" fill="currentColor"/>`
    +`<path fill="var(--bg)" fill-rule="evenodd" `
    +`transform="translate(${offsetX.toFixed(2)},${offsetY.toFixed(2)}) scale(${scale.toFixed(4)})" `
    +`d="${entry.d}"/></svg>`;
}
// Owner (2026-08-15): "i just saw a bug, with a pink dot on it overlapping
// the bug. just put a circle around the bug when there is a question as well
// (pink circle)." A story whose lifecycle glyph is a bug never wears the
// filled question dot — it wears a question-colored RING around the glyph.
// Pure seams so canvas, hit-testing, and the DOM-less suite share one truth.
function questionBadgeStyle(node){
  return (node||{}).g==='buggap'?'ring':'dot';
}
function questionRingGeometry(node,nodeRadiusValue){
  const severity=bugSeverity(node);
  const glyph=severity==='serious'?'exclamationmark.triangle':'ladybug';
  const box=symbolUnitBox(glyph);
  const glyphHeight=nodeRadiusValue*(severity==='serious'?2.7:2.1);
  const glyphWidth=glyphHeight*(box.w/box.h);
  // Enclose the glyph's whole box with a small clearance; a legibility floor
  // keeps the ring readable on tiny far-away stars (the dot had one too).
  return {glyph,radius:Math.max(9,Math.hypot(glyphWidth,glyphHeight)/2+1.5)};
}
// ---- attention rings (pure geometry, shared by canvas and the DOM-less suite) ----
// The question badge's established breathing cue, lifted out of the canvas so
// the parked-answer ring can be compared against it instead of guessed at.
function questionRingPulse(baseRadius,wave,reduced){
  return reduced
    ?{radius:baseRadius*1.4,alpha:.8,lineWidth:2}
    :{radius:baseRadius*(1.28+.24*wave),alpha:.35+.5*wave,lineWidth:1.5};
}
// Owner (2026-08-15): "the option to park answers is good, nice touch. can we
// flag those in the ui for the user to circle back to... make the outline
// larger, and pulse a little more?" A story holding a parked draft wears an
// OUTER ring — larger than the question cue it encircles — with a wider radius
// and contrast swing. prefers-reduced-motion gets a static emphasized ring: an
// attention cue, never a strobe, and the paint stays clock-deterministic.
function parkedRingGeometry(baseRadius){
  return {radius:Math.max(14,baseRadius*2.05),lineWidth:2.4};
}
function parkedRingPulse(baseRadius,wave,reduced){
  const outer=parkedRingGeometry(baseRadius).radius;
  return reduced
    ?{radius:outer*1.18,alpha:.92,lineWidth:3}
    :{radius:outer*(1+.34*wave),alpha:.4+.6*wave,lineWidth:2.6};
}
// Size is the severity channel for the review glyph: critical AND blocking
// renders larger ("if the review is critical and blocking, making it big is
// good"). Anything less keeps the fitted size.
function reviewGlyphScale(critical,blocking){
  return critical&&blocking?1.6:1;
}

// Developer Flow consumes Constellation's existing SF Symbol vocabulary rather
// than inventing a second set of kind glyphs. Object kind stays a text channel;
// lifecycle/status owns the icon channel until IllTool revises the catalog.
const ACTIVE_STATUSES=new Set(['active','building','in-flight']);
const BLOCKED_STATUSES=new Set(['blocked','bug-gap','error','failed']);
const BACKLOG_STATUSES=new Set(['backlog','idea','faint','unknown']);

export function lifecycleSymbolName(object={}){
  const status=String(object.status||'').toLowerCase();
  if(object.failure)return 'exclamationmark.triangle';
  if(BLOCKED_STATUSES.has(status)||object.statusRole==='blocked')return 'ladybug';
  if(status==='shipped'||status==='done'||object.statusRole==='shipped')return 'checkmark';
  if(status==='specced')return 'document';
  if(status==='parked')return 'parkingsign';
  if(BACKLOG_STATUSES.has(status))return 'lightbulb';
  if(ACTIVE_STATUSES.has(status)||object.statusRole==='active')return 'arrow.up.right';
  return '';
}

const SEMANTIC_OBJECT_SYMBOLS=[
  [/\b(test|tests|testing|verify|verification|contract check|acceptance)\b/,'checkmark.square'],
  [/\b(database|datastore|storage|index|sql|db)\b/,'cylinder'],
  [/\b(cloud|hosted|saas)\b/,'cloud'],
  [/\b(auth|authentication|authorization|security|secure|lock|permission)\b/,'lock'],
  [/\b(fps|performance|latency|speed|benchmark|throughput)\b/,'arrow.up.right'],
  [/\b(metric|measure|measurement|detect|detection|estimate|estimation|vanishing)\b/,'eyeglasses'],
  [/\b(component|instance|group|grouping|organization|dependency|branch)\b/,'arrow.trianglehead.branch'],
  [/\b(command|batch|transaction|automation|pipeline)\b/,'list.dash.header.rectangle'],
  [/\b(ai|ml|model|coreml|intelligent|prediction|predict|inference|vision)\b/,'sparkles'],
  [/\b(draw|drawing|geometry|path|curve|vector|shape|stroke|anchor|canvas|paint)\b/,'scribble.variable'],
  [/\b(ui|interface|view|panel|window|sidebar|toolbar|responsive|layout|grid|perspective|isometric)\b/,'rectangle.on.rectangle'],
  [/\b(service|server|api|endpoint|network|worker|provider)\b/,'server.rack'],
  [/\b(import|export|publish|upload|release)\b/,'arrow.up.baseline'],
  [/\b(review|inspect|audit|observe)\b/,'eyeglasses'],
  [/\b(bug|defect|crash|error|repair|fix)\b/,'ladybug'],
];

export function objectSymbolName(object={}){
  const text=[object.id,object.kind,object.title,object.summary].filter(Boolean)
    .join(' ').toLowerCase();
  for(const [pattern,name] of SEMANTIC_OBJECT_SYMBOLS)if(pattern.test(text))return name;
  if(/\b(capability|epic|cluster|module|group)\b/.test(text))return 'arrow.trianglehead.branch';
  return 'document';
}

export function groupSymbolName(){return 'list.dash.header.rectangle';}

export function sfSymbolPresentation(name){
  const entry=SYMBOL_OUTLINES[name];
  if(!entry)return null;
  const box=symbolUnitBox(name);
  return {name,d:entry.d,fillRule:entry.fillRule||'evenodd',box,
    viewBox:`0 0 ${box.w.toFixed(4)} ${box.h.toFixed(4)}`};
}
