import sqlite3, pandas as pd, os, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), '..', 'data', 'trading.db'))
trades = pd.read_sql('SELECT * FROM trades ORDER BY open_time DESC', conn)
open_t = trades[trades['is_closed']==0]
closed = trades[trades['is_closed']==1]
print(f'Total trades: {len(trades)} | Open: {len(open_t)} | Closed: {len(closed)}')
if len(closed) > 0:
    wins = closed[closed['profit'] > 0]
    losses = closed[closed['profit'] <= 0]
    total_profit = closed['profit'].sum()
    print(f'Win Rate: {len(wins)}/{len(closed)} = {len(wins)/len(closed)*100:.1f}%')
    print(f'Total P/L: ${total_profit:.2f}')
    print(f'Avg trade: ${closed["profit"].mean():.2f}')
    if len(losses)>0 and len(wins)>0:
        avg_win = wins['profit'].mean()
        avg_loss = abs(losses['profit'].mean())
        print(f'Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f} | R:R = {avg_win/avg_loss:.2f}')
    print()
    print('--- By Strategy ---')
    for strat, g in closed.groupby('strategy'):
        w = (g['profit']>0).sum()
        print(f'  {strat}: {len(g)} trades, WR={w/len(g)*100:.0f}%, P/L=${g["profit"].sum():.2f}')
    print()
    print('--- By Symbol ---')
    for sym, g in closed.groupby('symbol'):
        w = (g['profit']>0).sum()
        print(f'  {sym}: {len(g)} trades, WR={w/len(g)*100:.0f}%, P/L=${g["profit"].sum():.2f}')
    print()
    print('--- Last 10 Closed ---')
    for _, t in closed.head(10).iterrows():
        strat = str(t.get('strategy', ''))[:20]
        print(f'  {t["open_time"][:16]} {t["symbol"]:8s} {t["direction"]:4s} {strat:20s} ${t["profit"]:+.2f}')
snaps = pd.read_sql('SELECT * FROM account_snapshots ORDER BY timestamp DESC LIMIT 1', conn)
if len(snaps)>0:
    s = snaps.iloc[0]
    print(f'\nAccount: Balance=${s["balance"]:.2f} | Equity=${s["equity"]:.2f}')
conn.close()
