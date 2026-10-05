param(
    [string]$Source = 'docs/presentation/deck-content.json',
    [string]$Output = 'docs/presentation/DDM501_Defense_15p_Demo13p_QA10p.pptx',
    [string]$Preview = 'reports/presentation-build/slides'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$content = Get-Content -LiteralPath (Join-Path $root $Source) -Raw -Encoding UTF8 | ConvertFrom-Json
$final = Join-Path $root $Output
$previewDir = Join-Path $root $Preview
New-Item -ItemType Directory -Force (Split-Path $final), $previewDir | Out-Null
if (Test-Path -LiteralPath $final) { throw "Output already exists: $final" }

function Color([string]$hex) {
    $hex = $hex.TrimStart('#')
    return [Convert]::ToInt32($hex.Substring(0,2),16) + 256*[Convert]::ToInt32($hex.Substring(2,2),16) + 65536*[Convert]::ToInt32($hex.Substring(4,2),16)
}
$script:ink = Color '172F3C'
$script:muted = Color '526673'
$script:teal = Color '176E68'
$script:orange = Color 'BB542A'
$script:bg = Color 'F7F4ED'
$script:pale = Color 'E4EEEA'
$script:white = Color 'FFFFFF'
$script:lightOrange = Color 'F2DFD1'
$script:font = 'Segoe UI'
$script:checks = [System.Collections.Generic.List[object]]::new()

function Box($slide, $x, $y, $w, $h, [int]$fill, [int]$shapeType = 1) {
    $shape = $slide.Shapes.AddShape($shapeType, $x, $y, $w, $h)
    $shape.Fill.ForeColor.RGB = $fill
    $shape.Line.Visible = 0
    return $shape
}
function Txt($slide, $x, $y, $w, $h, [string]$value, [float]$size = 22, [int]$color = $script:ink, [bool]$bold = $false) {
    $shape = $slide.Shapes.AddTextbox(1, $x, $y, $w, $h)
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $shape.TextFrame.WordWrap = -1
    $shape.TextFrame.AutoSize = 0
    $range = $shape.TextFrame.TextRange
    $range.Text = $value
    $range.Font.Name = $script:font
    $range.Font.NameFarEast = $script:font
    $range.Font.Size = $size
    $range.Font.Color.RGB = $color
    $range.Font.Bold = [int](-[int]$bold)
    $range.ParagraphFormat.SpaceAfter = 7
    $range.ParagraphFormat.Bullet.Visible = 0
    return $shape
}
function Link($slide, $x1, $y1, $x2, $y2, [int]$color=$script:teal) {
    $line = $slide.Shapes.AddLine($x1,$y1,$x2,$y2)
    $line.Line.ForeColor.RGB=$color
    $line.Line.Weight=2
    $line.Line.EndArrowheadStyle=3
}
function Node($slide,$x,$y,$w,$h,$heading,$body,[int]$fill=$script:pale) {
    $null=Box $slide $x $y $w $h $fill
    $null=Txt $slide ($x+16) ($y+13) ($w-32) 32 $heading 23 $script:teal $true
    $null=Txt $slide ($x+16) ($y+53) ($w-32) ($h-60) $body 18
}
function Table($slide,$headers,$rows) {
    $rCount=$rows.Count+1
    $cCount=$headers.Count
    $height=[Math]::Min(322,44*$rCount)
    $shape=$slide.Shapes.AddTable($rCount,$cCount,46,148,868,$height)
    $table=$shape.Table
    if($cCount -eq 3) {
        $table.Columns.Item(1).Width=230
        $table.Columns.Item(2).Width=318
        $table.Columns.Item(3).Width=320
    } else {
        $table.Columns.Item(1).Width=315
        $table.Columns.Item(2).Width=553
    }
    for($r=1;$r -le $rCount;$r++) {
        for($c=1;$c -le $cCount;$c++) {
            $cell=$table.Cell($r,$c).Shape
            $cell.Fill.ForeColor.RGB=$(if($r -eq 1){$script:teal}elseif($r%2 -eq 0){$script:pale}else{$script:bg})
            $cell.TextFrame.MarginLeft=12
            $cell.TextFrame.MarginRight=10
            $cell.TextFrame.MarginTop=7
            $cell.TextFrame.MarginBottom=7
            $cell.TextFrame.VerticalAnchor=3
            $range=$cell.TextFrame.TextRange
            $range.Text=$(if($r -eq 1){$headers[$c-1]}else{$rows[$r-2][$c-1]})
            $range.Font.Name=$script:font
            $range.Font.Size=$(if($r -eq 1){19}else{18})
            $range.Font.Bold=$(if($r -eq 1){-1}else{0})
            $range.Font.Color.RGB=$(if($r -eq 1){$script:white}else{$script:ink})
            $range.ParagraphFormat.Bullet.Visible=0
            $range.ParagraphFormat.SpaceAfter=0
            foreach($edge in 1..4) { $table.Cell($r,$c).Borders.Item($edge).ForeColor.RGB=$script:bg }
        }
    }
}

$app = New-Object -ComObject PowerPoint.Application
$existing=$app.Presentations.Count
$deck=$app.Presentations.Add(0)
try {
    $deck.PageSetup.SlideWidth=960
    $deck.PageSetup.SlideHeight=540
    $index=0
    foreach($item in $content.slides) {
        $index++
        $slide=$deck.Slides.Add($index,12)
        $slide.FollowMasterBackground=0
        $slide.Background.Fill.ForeColor.RGB=$script:bg
        $null=Box $slide 46 25 52 5 $script:orange
        if($item.layout -ne 'cover') {
            $titleSize=$(if($item.title.Length -gt 76){30}else{32})
            $null=Txt $slide 46 43 868 91 $item.title $titleSize $script:ink $true
        }
        $null=Txt $slide 898 510 26 18 ([string]$index) 10 $script:muted
        if($item.footnote) { $null=Txt $slide 46 482 830 40 $item.footnote 12 $script:muted }
        switch($item.layout) {
            'cover' {
                $null=Txt $slide 46 73 610 150 $item.title 54 $script:ink $true
                $null=Txt $slide 48 270 600 46 $item.lines[0] 30 $script:teal $true
                $null=Txt $slide 48 326 570 85 $item.lines[1] 24
                $null=Txt $slide 48 451 820 26 'Trịnh Đức Dương    Do Quang Hiep    To Thanh Hai    Ngo Anh Duc' 16
                $null=Txt $slide 48 487 550 23 $item.lines[2] 13 $script:muted
                $null=Box $slide 712 105 130 130 $script:lightOrange 9
                $null=Box $slide 755 137 44 44 $script:orange 9
                $null=Box $slide 733 190 88 26 $script:orange 9
                foreach($j in 0..10) {
                    $height=20+54*[Math]::Abs([Math]::Sin($j*1.15))
                    $null=Box $slide (689+$j*17) (318-$height/2) 7 $height $script:teal
                }
            }
            'timeline' {
                $line=$slide.Shapes.AddLine(78,215,874,215)
                $line.Line.ForeColor.RGB=$script:orange
                $line.Line.Weight=3
                for($j=0;$j -lt 3;$j++) {
                    $x=46+$j*298
                    $null=Txt $slide $x 156 268 42 $item.items[$j][0] 28 $script:orange $true
                    $null=Box $slide ($x+10) 208 14 14 $script:orange 9
                    $null=Txt $slide $x 253 265 73 $item.items[$j][1] 25 $script:ink $true
                    $null=Txt $slide $x 343 265 96 $item.items[$j][2] 21
                }
            }
            'columns' {
                for($j=0;$j -lt 3;$j++) {
                    $x=46+$j*299
                    $null=Txt $slide $x 157 265 53 ('0'+($j+1)) 38 $script:orange $true
                    $null=Txt $slide $x 226 265 76 $item.items[$j][0] 26 $script:teal $true
                    $null=Txt $slide $x 326 265 132 $item.items[$j][1] 23
                }
            }
            'table' { Table $slide $item.headers $item.rows }
            'split' {
                $line=$slide.Shapes.AddLine(477,158,477,443)
                $line.Line.ForeColor.RGB=Color 'CCD6D1'
                for($j=0;$j -lt 2;$j++) {
                    $x=46+$j*463
                    $null=Txt $slide $x 169 399 64 $item.items[$j][0] 28 $script:teal $true
                    $null=Txt $slide $x 254 393 190 $item.items[$j][1] 25
                }
            }
            'flow' {
                for($j=0;$j -lt 5;$j++) {
                    $x=46+$j*177
                    $null=Txt $slide $x 182 156 38 ('0'+($j+1)) 27 $script:orange $true
                    $null=Box $slide $x 236 154 5 $script:teal
                    $null=Txt $slide $x 265 155 75 $item.items[$j][0] 24 $script:ink $true
                    $null=Txt $slide $x 351 155 98 $item.items[$j][1] 18
                    if($j -lt 4){ Link $slide ($x+151) 238 ($x+170) 238 }
                }
            }
            'models' {
                for($j=0;$j -lt 2;$j++) {
                    $y=160+$j*104
                    $null=Txt $slide 46 $y 110 32 $item.items[$j][0] 19 $script:orange $true
                    $null=Txt $slide 179 $y 100 34 $item.items[$j][1] 24
                    Link $slide 282 ($y+17) 330 ($y+17)
                    $null=Txt $slide 351 $y 225 34 $item.items[$j][2] 23 $script:teal $true
                    Link $slide 592 ($y+17) 637 ($y+17)
                    $null=Txt $slide 657 $y 257 59 $item.items[$j][3] 22
                }
                $null=Box $slide 46 369 868 79 $script:pale
                $null=Txt $slide 63 382 834 59 ($item.lines -join '  /  ') 19
            }
            'architecture' {
                Node $slide 46 164 188 121 $item.items[0][0] $item.items[0][1]
                Node $slide 292 164 263 121 $item.items[1][0] $item.items[1][1]
                Node $slide 624 164 290 121 $item.items[2][0] $item.items[2][1]
                Node $slide 292 338 263 114 $item.items[3][0] $item.items[3][1]
                Node $slide 624 338 290 114 $item.items[4][0] $item.items[4][1]
                Link $slide 234 218 285 218
                Link $slide 555 218 617 218
                Link $slide 769 285 769 331
                $line=$slide.Shapes.AddLine(712,285,712,310)
                $line.Line.ForeColor.RGB=$script:teal
                $line.Line.Weight=2
                $line=$slide.Shapes.AddLine(424,310,712,310)
                $line.Line.ForeColor.RGB=$script:teal
                $line.Line.Weight=2
                Link $slide 424 310 424 331
                Link $slide 555 396 617 396
                $null=Txt $slide 46 350 206 85 'Policy state bền vững và audit từng bước' 22 $script:orange $true
            }
            'lifecycle' {
                for($j=0;$j -lt 6;$j++) {
                    $x=46+$j*147
                    $null=Txt $slide $x 185 137 52 $item.items[$j][0] 22 $script:teal $true
                    $null=Box $slide $x 254 125 5 $script:teal
                    $null=Txt $slide $x 282 133 92 $item.items[$j][1] 19
                    if($j -lt 5){ Link $slide ($x+125) 256 ($x+141) 256 }
                }
                $null=Box $slide 46 392 868 55 $script:lightOrange
                $null=Txt $slide 62 402 836 34 'Gate fail: dừng challenger, giữ hoặc phục hồi champion' 23 $script:orange $true
            }
            'gates' {
                $null=Txt $slide 46 150 868 67 $item.lines[0] 42 $script:teal $true
                for($j=1;$j -lt $item.lines.Count;$j++) {
                    $null=Box $slide 48 (244+($j-1)*53) 6 25 $script:orange
                    $null=Txt $slide 74 (239+($j-1)*53) 829 42 $item.lines[$j] 24
                }
            }
            'evidence' {
                for($j=0;$j -lt 3;$j++) {
                    $x=46+$j*299
                    $null=Txt $slide $x 173 273 86 $item.items[$j][0] 52 $script:teal $true
                    $null=Txt $slide $x 275 260 62 $item.items[$j][1] 25 $script:ink $true
                    $null=Txt $slide $x 355 260 96 $item.items[$j][2] 21
                }
            }
            'demo' {
                for($j=0;$j -lt 3;$j++) {
                    $y=157+$j*102
                    $null=Txt $slide 46 $y 76 65 $item.items[$j][0] 39 $script:orange $true
                    $null=Txt $slide 143 $y 766 50 $item.items[$j][1] 27 $script:teal $true
                    $null=Txt $slide 143 ($y+53) 766 40 $item.items[$j][2] 20
                }
            }
            'rollback' {
                $null=Txt $slide 46 161 354 88 $item.lines[0] 59 $script:orange $true
                $null=Txt $slide 46 255 354 49 $item.lines[1] 23
                $null=Txt $slide 46 323 364 67 $item.lines[2] 48 $script:teal $true
                $null=Txt $slide 46 402 364 47 $item.lines[3] 21
                $null=Txt $slide 477 212 420 201 $item.lines[4] 27 $script:ink $true
            }
            'closing' {
                foreach($j in 0..2) {
                    $null=Txt $slide 47 (186+$j*84) 852 65 $item.lines[$j] 31 $script:teal ($j -eq 2)
                }
            }
            'formula' {
                for($j=0;$j -lt $item.lines.Count;$j++) {
                    $size=$(if($j%2 -eq 0){24}else{20})
                    $null=Txt $slide 46 (150+$j*51) 868 40 $item.lines[$j] $size
                }
            }
            'sources' {
                for($j=0;$j -lt $item.lines.Count;$j++) {
                    $null=Txt $slide 46 (151+$j*61) 868 50 $item.lines[$j] 23
                }
            }
        }
        $notes="Nguoi trinh bay: $($item.speaker)`r`nThoi luong: $($item.seconds) giay`r`n`r`n$($item.notes)`r`n`r`nTHAO TAC: $($item.cue)`r`n`r`nNGUON:`r`n$($item.sources -join "`r`n")"
        $slide.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text=$notes
        if($item.hidden){ $slide.SlideShowTransition.Hidden=-1 }
        for($k=1;$k -le $slide.Shapes.Count;$k++) {
            $shape=$slide.Shapes.Item($k)
            if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                $overflow=$shape.TextFrame.TextRange.BoundHeight - $shape.Height
                if($overflow -gt 2){$script:checks.Add(@{slide=$index;shape=$k;overflow=$overflow;text=$shape.TextFrame.TextRange.Text})}
            }
        }
    }
    $deck.SaveAs($final,24)
    $deck.Export($previewDir,'PNG',1280,720)
    $pdf=[System.IO.Path]::ChangeExtension($final,'.pdf')
    $deck.SaveAs($pdf,32)
    $script:checks | ConvertTo-Json -Depth 5 | Set-Content (Join-Path (Split-Path $previewDir) 'text-overflow.json') -Encoding UTF8
    Write-Output "Created $final"
    Write-Output "Created $pdf"
    Write-Output "Slides: $($deck.Slides.Count); text overflow flags: $($script:checks.Count)"
} finally {
    $deck.Close()
    if($existing -eq 0){$app.Quit()}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($deck) | Out-Null
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
