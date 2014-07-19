#! /bin/sh

######################################################################
#
# MAKE_POSTAGE_TABLE.SH
# 送料表を作成する
# Written by Matsuura(richmikan@richlab.org) at 2013/10/21
#
# [引数] MAKE_POSTAGE_TABLE.SH [-d 注文日] <カゴファイル>
# ・カゴファイルは次の仕様であること
#   - 商品ID カゴ入り数量 という行を0行以上含んでいること
# ・[注文日]にて指定された、年月日に既に発売日を過ぎている商品、および
#   発売日が注文日から$TR_MAX_POSTPOING_DAYS日先までのものは、まとめて
#   発送するものとして計算される。
#   - デフォルトは、このコマンドの実行日が注文日である。
#
# [入力]
# ・上記カゴファイル
# ・商品マスターファイル($File_PRODUCTS)
# ・厚さに基づく送料表($TR_File_postage_mm)
# ・重さに基づく送料表($TR_File_postage_g)
#
# [出力]
# ・列構成
#   - 1:発送時期(0なら1週間以内に) 2:その時の送料(円) 3:発送手段
# ・最後の行に下記のような合計行
#   - 1:"合計" 2:合計送料 3:"-"
# を返す
#
######################################################################


######################################################################
# 初期設定
######################################################################

# --- このシステム(CART)のホームディレクトリー -----------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d.."; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
# 1)Tukubaiパス、その他共通定義
. $Homedir/CONFIG/COMMON.SHLIB  # Tukubaiパス、その他共通定義
. $Homedir/CONFIG/TRADING.SHLIB # このお店の取り引きルール定義
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- 送料に関する各種設定 -------------------------------------------
# 1)このシステムでの取り扱い範囲外値を設定
#   (このような場合に無料にするか、別途問い合わせにするかは任意)
readonly toothick=999999     # 取扱範囲外の厚さとしての便宜的な値
readonly tooheavy=999999     # 取扱範囲外の重さとしての便宜的な値
readonly tooexpensive=999999 # 取扱範囲外の送料としての便宜的な値
# 2)$MAX_POSTPOING_DAYS日後の日付(発売日まで$MAX_POSTPOING_DAYS日以内の
#   商品の発送を一まとめにするため)
date_send=$(date '+%Y%m%d'                                    |
            calclock 1 -                                      |
            awk '{print $2+86400*'"$TR_MAX_POSTPOING_DAYS"'}' |
            calclock -r 1 -                                   |
            awk '{print substr($2,1,8)}'                      )

# --- エラー終了関数定義 ---------------------------------------------
error_exit() {
  [ -n "$2" ] && echo "${0##*/}: $2" 1>&2
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit $1
}

# --- 走行ログ記録開始設定 -------------------------------------------
if [ -z "$DISABLE_SHLOG" ]; then
  timestamp=$(date '+%Y%m%d %H%M%S')
  timestamp_date=${timestamp% *}
  timestamp_time=${timestamp#* }
  Execlogdir=$Dir_LOG/${timestamp_date%[0-9][0-9][0-9][0-9]}/${timestamp_date#[0-9][0-9][0-9][0-9]}/SHELL
  ([ "$SUEXEC_MODE" -eq 0 ] && umask 0000; mkdir -p "$Execlogdir")
  [ $? -eq 0 ] || error_exit 1 'log directory is not available'
  touch "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || error_exit 1 'Fail to create a logfile'
  [ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  gzpipe $Tmp-gzlogpipe "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || error_exit 1 'Fail to create a pipe for logging'
  exec 2> $Tmp-gzlogpipe
  set -xv
fi


######################################################################
# 引数確認
######################################################################

# --- 発送予定日オプションがあれば取得する ---------------------------
if [ \( -n "_$1" \) -a \( "_$1" = '_-d' \)  ]; then
  shift
  if echo "_$1" | grep '^_[0-9]\{8,8\}$' >/dev/null; then
    date_send=$(echo $1                                           |
                calclock 1 -                                      |
                awk '{print $2+86400*'"$TR_MAX_POSTPOING_DAYS"'}' |
                calclock -r 1 -                                   |
                awk '{print substr($2,1,8)}'                      )
    shift
  else
    error_exit 2 'Invalid "-d" option'
  fi
fi

# --- 引数の数を確認 -------------------------------------------------
if [ $# -gt 1 ]; then
  error_exit 3 'Invalid argument'
fi

# --- 引数で指定された文字列が有効なファイルであることを確認 ---------
if [ $# -eq 0 ]; then
  file='-'
elif [ \( -f "$1" \) -o \( -c "$1" \) -o \( -p "$1" \) -o \( "_$1" = '_-' \) ]; then
  file=$1
else
  error_exit 4 'No such file found'
fi


######################################################################
# ファイルの正規化
######################################################################

# --- 商品マスターファイルを正規化してコピー -------------------------
# 1)存在確認
[ -f "$File_PRODUCTS" ] || error_exit 5 'product mster file is not found'
# 2)正規化
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
sort -k1,1                            |
self 1 3 4 5 6                        |
# 1:商品ID* 2:単価(+税表記含) 3:発売日 4:大きさ情報体 5:在庫情報体
awk '{sub(/\+[Tt]$/, "", $2)} 1'      > $Tmp-productmaster # "+税"表記を単純に除去
# 1:商品ID* 2:単価(売上単価) 3:発売日 4:大きさ情報体 5:在庫情報体

# --- カゴファイルを正規化してコピー ---------------------------------
# 1)商品行だけ取り出す
if [ "_${file%.gz}" != "_$file" ]; then zcat "$file"; else cat "$file"; fi |
grep '^[A-Za-z0-9_-]\+[[:blank:]][0-9]\+$'                                 |
sort -k1,1                                                                 > $Tmp-cart
# 1:商品ID* 2:カゴ入り数量
# 2)その結果、1行も無い(カゴが空だった)時は終了
if [ $(gyo $Tmp-cart) -eq 0 ]; then
  echo '合計 0 商品無し'
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi

######################################################################
# 買い物合計金額による送料無料化処理
######################################################################

# --- 合計金額が所定額以上なら無料にして終了 -------------------------
total=$(cat $Tmp-cart                                                  |
        # 1:商品ID 2:カゴ入り数量                                      #
        #join1 key=1 $Tmp-productmaster                                 |
        join -1 1 -2 1 -o 2.1,1.2,1.3,1.4,1.5,2.2 $Tmp-productmaster - |
        # 1:商品ID 2:単価 3:発売日 4:大きさ情報体 5:在庫情報体 6:カゴ入り数量
        awk '{total+=$2*$6} END{print total}'                          )
if [ $total -ge $TR_POSTAGEFREE_PRICE ]; then
  echo '合計 0 送料無料'
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0
fi


######################################################################
# 通常の送料計算
######################################################################

# --- 実際に発送する商品のサイズ一覧表を作成する ---------------------
# 1)在庫情報体に基づき、実際に発送する商品IDに展開
#   ただし送料free商品や大きさ0商品、カゴに入ってない商品はここで除去する
cat "$Tmp-productmaster"                                             |
#join2 +0 key=1 "$Tmp-cart"                                           |
join -1 1 -2 1 -a 2 -o 2.1,1.2,2.2,2.3,2.4,2.5 "$Tmp-cart" -         |
sed 's/  / 0 /g'                                                     |
sed 's/  / 0 /g'                                                     |
# 1:商品ID 2:カゴ入り数量 3:単価 4:発売日 5:大きさ情報体 6:在庫情報体#
awk '                                                                #
  {                                                                  #
    if (NF<6) {err=1; exit 1;}                                       #
    pids[$1] = 1; qty[$1] = $2; reldate[$1] = $4;                    #
    volinfo[$1] = tolower($5); stockinfo[$1] = $6;                   #
  }                                                                  #
  END {                                                              #
    if (err!=0) {exit err;}                                          #
    for (pid in pids) {                                              #
      if (qty[pid] == 0) {continue;} # カゴ入り数が0の商品は無視     #
      if (match(volinfo[pid],/^free$/)) {continue;} # 送料0商品も無視#
      split(stockinfo[pid], demand_pids, ",");                       #
      for (i in demand_pids) {                                       #
        if (match(demand_pids[i],/^[@*]$/)) {                        #
          print pid, qty[pid], reldate[pid], volinfo[pid];           #
        } else {                                                     #
          if (! demand_pids[i] in pids) {exit 1;}                    #
          dpid=demand_pids[i];                                       #
          print dpid, qty[pid], reldate[dpid], volinfo[dpid];        #
        }                                                            #
      }                                                              #
    }                                                                #
  }'                                                                 > $Tmp-extcart
# 1:商品ID 2:カゴ入り数量 3:発売日 4:大きさ情報体                    #
[ $? -eq 0 ] || error_exit 6 'invalid product master file'
# 2)大きさ情報体を重さと厚みに展開
cat $Tmp-extcart                                                        |
grep -v '[[:blank:]]0$'                                                 | # 展開後の大きさ情報体が0の物は除外
awk '                                                                   #
  {                                                                     # 厚み,重さがそれぞれ
    thickness='$toothick'; weight='$tooheavy';                          # 未定義のものは巨大という
    split($4, sizes, ",");                                              # 設定にしておく
    for (i in sizes) {                                                  #
      if        (match(sizes[i], /^([0-9]+(\.[0-9]+)?|\.[0-9]+)mm$/)) { #
        thickness = substr(sizes[i],1,RLENGTH) * 1;                     #
      } else if (match(sizes[i], /^([0-9]+(\.[0-9]+)?|\.[0-9]+)cm$/)) { #
        thickness = substr(sizes[i],1,RLENGTH) * 10;                    #
      } else if (match(sizes[i], /^([0-9]+(\.[0-9]+)?|\.[0-9]+)g$/ )) { #
        weight = substr(sizes[i],1,RLENGTH) * 1;                        #
      } else if (match(sizes[i], /^([0-9]+(\.[0-9]+)?|\.[0-9]+)kg$/)) { #
        weight = substr(sizes[i],1,RLENGTH) * 1000;                     #
      }                                                                 #
    }                                                                   #
    print $1, $2, $3, thickness, weight;                                #
  }'                                                                    |
# 1:商品ID 2:カゴ入り数量 3:発売日 4:厚み(mm) 5:重量(g)                 #
grep -v ' 0 0$'                                                         | # 厚み=重さ=0の商品は除外
self 3 4 5 2                                                            | # 発売日,サイズ,数量に入替
sort -k1n,1                                                             > $Tmp-reldate_pid_sizes_qty
# 1:発売日 2:厚み(mm) 3:重量(g) 4:カゴ入り数量

# --- 発売日に基づいてまとられるものは、厚み・重量をまとめる ---------
# (発売済～1週間先発売のものまでの一まとめにする)
cat $Tmp-reldate_pid_sizes_qty                                   |
awk '                                                            #
  BEGIN{s="'"$date_send"'までに";}                               #
  $1<='"$date_send"'{mm+=$2*$4; g+=$3*$4;next;}                  #
  {if((mm+g)>0){print s,mm,g; mm=0; g=0;} print $1,$2*$4,$3*$4;} #
  END{if((mm+g)>0){print s,mm,g;}}'                              > $Tmp-gatherd_sizes
# 1:製品発送時期(発売日) 2:その時発送分総厚み(mm) 3:その時発送分総重量(g)

# --- 各々に送料を当てはめる -----------------------------------------
# 1)厚さ・重さ対値段定義ファイルの存在確認
[ -f "$TR_File_postage_g" ]  || error_exit 7 'weight-price table file is not found'
[ -f "$TR_File_postage_mm" ] || error_exit 8 'thickness-price table file is not found'
# 2)厚さ・重さを価格と手段に変換
cat $Tmp-gatherd_sizes                                            |
awk '                                                             #
  BEGIN {                                                         #
    i = 1;                                                        #
    while (getline line < "'"$TR_File_postage_mm"'") {            #
      sub(/[[:blank:]]+#.*$/,line);                               #
      split(line, ar);                                            #
      mm_rank[i]=ar[1]; mm2p[ar[1]] = ar[2]; mm2m[ar[1]] = ar[3]; #
      i++;                                                        #
    }                                                             #
    i = 1;                                                        #
    while (getline line < "'"$TR_File_postage_g"'") {             #
      sub(/[[:blank:]]+#.*$/,line);                               #
      split(line, ar);                                            #
      g_rank[i]=ar[1]; g2p[ar[1]] = ar[2]; g2m[ar[1]] = ar[3];    #
      i++;                                                        #
    }                                                             #
  }                                                               #
  function mm2p_and_m(mm) {                                       #
    for (i=1; i<=length(mm_rank); i++) {                          #
      if (mm > mm_rank[i]) {continue;}                            #
      return mm2p[mm_rank[i]] "," mm2m[mm_rank[i]];               #
    }                                                             #
    return '$tooexpensive' ",別途お見積";                         #
  }                                                               #
  function g2p_and_m(g) {                                         #
    for (i=1; i<=length(g_rank); i++) {                           #
      if (g > g_rank[i]) {continue;}                              #
      return g2p[g_rank[i]] "," g2m[g_rank[i]];                   #
    }                                                             #
    return '$tooexpensive' ",別途お見積";                         #
  }                                                               #
  {print $1, mm2p_and_m($2), g2p_and_m($3);}                      #
'                                                                 > $Tmp-postages
# 1:製品発送時期(発売日) 2:厚さに基づく値段,手段 3:重さに基づく値段,手段

# --- 送料表を作る ---------------------------------------------------
cat $Tmp-postages                                                   |
awk '                                                               #
  BEGIN {total=0;}                                                  #
  {                                                                 #
    split($2, mm_p_and_m, ","); split($3, g_p_and_m, ",");          #
    # 厚さと重さで送料の安い方を選択                                #
    if (g_p_and_m[2] < mm_p_and_m[2]) {                             #
      print $1, g_p_and_m[1],  g_p_and_m[2];  total+=g_p_and_m[1];  #
    } else {                                                        #
      print $1, mm_p_and_m[1], mm_p_and_m[2]; total+=mm_p_and_m[1]; #
    }                                                               #
  }                                                                 #
  END {print "合計",total,"-";}'                                    |
comma 2                                                             |
awk '{s=$2;gsub(/,/,"",s);                                          #
      if(s>='$tooexpensive'){$2=-1;$3="別途お見積"}                 #
      print;                                 }'                     |
# 1:製品発送時期(発売日) 2:送料 3:手段発送手段                      #
keta -14 10 -1


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
