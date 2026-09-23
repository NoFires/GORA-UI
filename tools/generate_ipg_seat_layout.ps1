param(
	[string]$OutputPath = (Join-Path $PSScriptRoot '..\gui\gora_ipg_seat_layout.gui')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Canonical 300-seat hemicycle geometry. This table is deliberately shared by
# all three canvases so a regeneration cannot make the views drift apart.
$PositionData = @'
410,204;427,204;444,204;461,204;478,204;495,204;494,193;477,193;460,193;393,204;376,204;409,193;426,193;443,193;476,182;493,182;491,171;474,171;459,182;441,182;424,182;391,193;374,192;406,182;439,171;456,171;471,160;489,160;485,150;453,160;421,171;388,181;370,181;403,171;435,160;449,150;467,150;482,139;477,129;463,139;445,139;431,150;417,160;384,170;398,160;412,150;426,140;459,129;472,119;467,109;453,119;439,130;379,160;365,170;392,150;406,140;420,130;433,120;447,110;461,100;454,91;441,101;427,111;413,121;399,131;385,141;358,161;372,151;420,102;434,92;447,82;440,74;426,84;406,112;392,122;378,132;364,142;384,114;398,104;412,94;418,76;432,66;423,59;409,69;403,87;389,97;369,125;349,152;355,135;375,107;395,80;415,52;405,46;400,63;385,73;380,90;360,118;340,145;345,129;365,101;370,84;376,68;391,57;396,40;386,35;381,51;360,79;355,96;350,112;329,140;334,124;365,63;371,47;376,30;366,26;360,43;355,59;350,75;345,91;339,107;328,104;334,88;339,71;344,55;350,39;355,23;344,20;339,36;333,53;323,120;318,136;317,101;323,85;328,69;328,34;333,18;322,16;317,33;322,51;317,67;311,84;312,118;306,134;306,100;306,66;311,49;306,32;311,15;300,15;300,49;300,83;300,117;294,134;294,100;294,66;289,49;294,32;289,15;278,16;283,33;278,51;283,67;289,84;288,118;283,101;277,85;272,69;272,34;267,18;256,20;261,36;267,53;277,120;282,136;272,104;266,88;261,71;256,55;250,39;245,23;234,26;240,43;245,59;250,75;255,91;261,107;271,140;266,124;235,63;229,47;224,30;214,35;219,51;240,79;245,96;250,112;255,129;235,101;230,84;224,68;209,57;204,40;195,46;200,63;215,73;220,90;240,118;260,145;245,135;225,107;205,80;185,52;177,59;191,69;197,87;211,97;231,125;251,152;236,142;216,114;202,104;188,94;182,76;168,66;160,74;174,84;194,112;208,122;222,132;242,161;228,151;180,102;166,92;153,82;146,91;159,101;173,111;187,121;201,131;215,141;208,150;194,140;180,130;167,120;153,110;139,100;133,109;147,119;161,130;221,160;235,170;202,160;188,150;174,140;141,129;128,119;123,129;137,139;155,139;169,150;183,160;216,170;230,181;197,171;165,160;151,150;133,150;118,139;115,150;147,160;179,171;212,181;226,192;194,182;161,171;144,171;129,160;111,160;109,171;126,171;141,182;159,182;176,182;209,193;191,193;174,193;157,193;124,182;107,182;106,193;123,193;140,193;207,204;224,204;190,204;173,204;156,204;139,204;122,204;105,204
'@

$Positions = @(
	$PositionData.Trim().Split(';') | ForEach-Object {
		$Coordinates = $_.Split(',')
		if ($Coordinates.Count -ne 2) {
			throw "Invalid seat coordinate: $_"
		}
		[pscustomobject]@{
			X = [int]$Coordinates[0]
			Y = [int]$Coordinates[1]
		}
	}
)

if ($Positions.Count -ne 300) {
	throw "Expected exactly 300 seat positions, got $($Positions.Count)."
}

function New-InterestGroupBranch {
	param(
		[string]$PointerVariable,
		[string]$SeatMaxVariable,
		[int]$SeatIndex
	)

	$Pointer = "Country.MakeScope.Var('$PointerVariable')"
	$Scope = "$Pointer.GetInterestGroup"
	[pscustomobject]@{
		Condition = "And($Pointer.IsSet, GreaterThanOrEqualTo_CFixedPoint($Scope.MakeScope.Var('$SeatMaxVariable').GetValue, '(CFixedPoint)$SeatIndex'))"
		Color = "$Scope.GetColor"
	}
}

function New-PartyBranch {
	param(
		[string]$PointerVariable,
		[string]$SeatMaxVariable,
		[int]$SeatIndex
	)

	$Pointer = "Country.MakeScope.Var('$PointerVariable')"
	$Scope = "$Pointer.GetParty"
	[pscustomobject]@{
		Condition = "And($Pointer.IsSet, GreaterThanOrEqualTo_CFixedPoint($Scope.MakeScope.Var('$SeatMaxVariable').GetValue, '(CFixedPoint)$SeatIndex'))"
		Color = "$Scope.GetColor"
	}
}

function New-CountryVariableBranch {
	param(
		[string]$SeatMaxVariable,
		[string]$Color,
		[int]$SeatIndex
	)

	$Variable = "Country.MakeScope.Var('$SeatMaxVariable')"
	[pscustomobject]@{
		Condition = "And($Variable.IsSet, GreaterThanOrEqualTo_CFixedPoint($Variable.GetValue, '(CFixedPoint)$SeatIndex'))"
		Color = $Color
	}
}

function New-ColorSelector {
	param(
		[object[]]$Branches,
		[string]$FallbackColor
	)

	$Expression = $FallbackColor
	for ($Index = $Branches.Count - 1; $Index -ge 0; $Index--) {
		$Branch = $Branches[$Index]
		$Expression = "Select_CVector4f( $($Branch.Condition), $($Branch.Color), $Expression )"
	}
	"[$Expression]"
}

function Get-PowerTint {
	param([int]$SeatIndex)

	$Branches = @(
		1..12 | ForEach-Object {
			New-InterestGroupBranch -PointerVariable "ipg_power_rank_$($_)_ig" -SeatMaxVariable 'power_seat_max' -SeatIndex $SeatIndex
		}
	)
	New-ColorSelector -Branches $Branches -FallbackColor "'(CVector4f)0,0,0,0'"
}

function Get-AlignmentTint {
	param([int]$SeatIndex)

	$Branches = @(
		1..12 | ForEach-Object {
			New-InterestGroupBranch -PointerVariable "ipg_alignment_rank_$($_)_ig" -SeatMaxVariable 'alignment_seat_max' -SeatIndex $SeatIndex
		}
		New-CountryVariableBranch -SeatMaxVariable 'ipg_alignment_other_max' -Color "'(CVector4f)0.30,0.30,0.30,1.00'" -SeatIndex $SeatIndex
	)
	New-ColorSelector -Branches $Branches -FallbackColor "'(CVector4f)0.55,0.55,0.55,1.00'"
}

function Get-ElectoralTint {
	param([int]$SeatIndex)

	$Branches = @(
		1..8 | ForEach-Object {
			New-PartyBranch -PointerVariable "ipg_electoral_party_rank_$($_)_party" -SeatMaxVariable 'electoral_seat_max' -SeatIndex $SeatIndex
		}
		1..6 | ForEach-Object {
			New-InterestGroupBranch -PointerVariable "ipg_electoral_ig_rank_$($_)_ig" -SeatMaxVariable 'electoral_seat_max' -SeatIndex $SeatIndex
		}
	)
	New-ColorSelector -Branches $Branches -FallbackColor "'(CVector4f)0.55,0.55,0.55,1.00'"
}

function Add-SeatCanvas {
	param(
		[System.Collections.Generic.List[string]]$Lines,
		[string]$TypeName,
		[string]$VisibleBinding,
		[scriptblock]$TintFactory
	)

	$Tab = [string][char]9
	$Tab2 = $Tab + $Tab
	$Tab3 = $Tab2 + $Tab
	$Lines.Add($Tab + "type $TypeName = widget {")
	$Lines.Add($Tab2 + 'size = { 600 230 }')
	$Lines.Add($Tab2 + 'max_update_rate = 4')
	$Lines.Add($Tab2 + 'visible = "' + $VisibleBinding + '"')

	for ($SeatIndex = 0; $SeatIndex -lt $Positions.Count; $SeatIndex++) {
		$Position = $Positions[$SeatIndex]
		$Tint = & $TintFactory $SeatIndex
		$Lines.Add($Tab2 + 'icon = {')
		$Lines.Add($Tab3 + 'texture = "gfx/interface/icons/ipg_white_circle.dds"')
		$Lines.Add($Tab3 + 'tintcolor = "' + $Tint + '"')
		$Lines.Add($Tab3 + 'size = { 12 12 }')
		$Lines.Add($Tab3 + "position = { $($Position.X) $($Position.Y) }")
		$Lines.Add($Tab2 + '}')
	}
	$Lines.Add($Tab + '}')
}

$Lines = [System.Collections.Generic.List[string]]::new()
$Lines.Add('# =============================================================================')
$Lines.Add('# GORA UI+ - Improved Parliament Graph: generated 300-seat canvases')
$Lines.Add('# Generated by tools/generate_ipg_seat_layout.ps1; do not hand-edit.')
$Lines.Add('# Three views x 300 physical icons = 900 icons total.')
$Lines.Add('# =============================================================================')
$Lines.Add('')
$Lines.Add('types politics_panel_types')
$Lines.Add('{')
$Tab = [string][char]9
$Lines.Add($Tab + '# Power: 12 IG rank bands, transparent only before the first snapshot.')
Add-SeatCanvas -Lines $Lines -TypeName 'ipg_seats_power' -VisibleBinding "[Country.MakeScope.Var('ipg_power_rank_1_ig').IsSet]" -TintFactory (Get-Item Function:\Get-PowerTint).ScriptBlock
$Lines.Add('')
$Lines.Add($Tab + '# Alignment: 12 IG bands, other aligned, then unaligned.')
Add-SeatCanvas -Lines $Lines -TypeName 'ipg_seats_alignment' -VisibleBinding "[Country.MakeScope.Var('ipg_alignment_unaligned_max').IsSet]" -TintFactory (Get-Item Function:\Get-AlignmentTint).ScriptBlock
$Lines.Add('')
$Lines.Add($Tab + '# Electoral: 8 party bands, 6 independent IG bands, then other.')
Add-SeatCanvas -Lines $Lines -TypeName 'ipg_seats_electoral' -VisibleBinding "[Country.MakeScope.Var('ipg_electoral_other_max').IsSet]" -TintFactory (Get-Item Function:\Get-ElectoralTint).ScriptBlock
$Lines.Add('}')

$ResolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$OutputDirectory = [System.IO.Path]::GetDirectoryName($ResolvedOutputPath)
if (-not [System.IO.Directory]::Exists($OutputDirectory)) {
	[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
}

$Utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
$NewLine = [string][char]10
$Content = [string]::Join($NewLine, $Lines) + $NewLine
[System.IO.File]::WriteAllText($ResolvedOutputPath, $Content, $Utf8WithoutBom)

Write-Output "Generated $($Positions.Count * 3) icons at $ResolvedOutputPath"
