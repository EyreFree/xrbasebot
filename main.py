import os
from dotenv import load_dotenv
import discord
import sqlite3
import requests

load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
client = discord.Client(intents=intents)

def create_table():
    conn = sqlite3.connect('user_accounts.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS accounts
                 (user_id TEXT PRIMARY KEY, github_id TEXT)''')
    
    conn.commit()
    conn.close()

def update_github_id(user_id, github_id):
    conn = sqlite3.connect('user_accounts.db')
    c = conn.cursor()

    # 检查是否存在目标用户的记录
    c.execute('SELECT COUNT(*) FROM accounts WHERE user_id = ?', (user_id,))
    count = c.fetchone()[0]

    if count == 0:
        # 如果记录不存在，插入一条新的记录
        c.execute('INSERT INTO accounts (user_id, github_id) VALUES (?, ?)', (user_id, github_id))
    else:
        # 如果记录存在，更新 GitHub ID
        c.execute('UPDATE accounts SET github_id = ? WHERE user_id = ?', (github_id, user_id))

    conn.commit()
    conn.close()

def get_github_id(user_id):
    conn = sqlite3.connect('user_accounts.db')
    c = conn.cursor()

    # 查询目标用户的记录，并返回对应的 github_id
    c.execute('SELECT github_id FROM accounts WHERE user_id = ?', (user_id,))
    result = c.fetchone()

    conn.close()

    if result:
        return result[0]
    else:
        return None

async def send_issues(channel, issues):
    target_issues = []
    for issue in issues:
        if "/pull" not in issue['html_url']:
            target_issues.append(issue)

    if len(target_issues) > 0:
        for issue in target_issues:
            title = issue['title']
            url = issue['html_url']
            body = issue.get('body')
            if not body:
                body = '无描述'
            author = issue['user']['login']
            
            await channel.send(f"**{title}**\n作者：{author}\n描述：{body}\nURL：{url}\n")
    else:
        await channel.send('目前没有待处理的任务')

def get_assigned_issue_ids(issues, github_id):
    assigned_issue_ids = []
    for issue in issues:
        if "/pull" not in issue['html_url']:
            assignees = issue.get('assignees', [])
            assignee_logins = [assignee['login'] for assignee in assignees]
            if github_id in assignee_logins:
                issue_id = issue['id']
                assigned_issue_ids.append(issue_id)
    return assigned_issue_ids

@client.event
async def on_ready():
    create_table()
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    # 无视机器人自己的消息
    if message.author == client.user:
        return

    # 调试用：看看这条消息
    await message.channel.send(message)

    # 是否为私聊
    is_private_chat = isinstance(message.channel, discord.DMChannel)

    if message.content.startswith('$'):
        command = message.content[1:]  # 获取命令名，去除前缀 $

        # info: 列出我的所有信息
        #   - GitHub 账号
        #   - 已领取的任务(根据 GitHub)
        if command == 'info':
            # 处理 $info 命令
            
            # 根据 discord_id 获取对应的 github_id
            discord_id = message.author.id
            github_id = get_github_id(discord_id)

            if github_id:
                await message.channel.send(f'您绑定的 GitHub ID 是: {github_id}')

                # 获取仓库的名称
                repo_owner = 'SwiftGGTeam'
                repo_name = 'the-swift-programming-language-in-chinese'
                
                # 调用 GitHub API 获取仓库的所有 open issue
                response = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues?state=open")
                
                # 检查 API 响应状态码
                if response.status_code == 200:
                    issues = response.json()
                    # 对获取到的 issue 进行处理并发送 issue ID
                    assigned_issue_ids = get_assigned_issue_ids(issues, github_id)
                    
                    if assigned_issue_ids:
                        await message.channel.send(f'指派给您的任务 ID 为：\n{", ".join(map(str, assigned_issue_ids))}')
                    else:
                        await message.channel.send(f'目前没有找到指派给您的任务')
                else:
                    await message.channel.send(f'获取任务列表失败：{response.json()}')
                    
            else:
                await message.channel.send('您尚未绑定 GitHub ID，请执行 bind [github_id] 命令进行绑定')
            pass

        # bind: 绑定 GitHub 账号
        elif command.startswith('bind'):
            # 处理 $bind 命令
            
            # 使用空格将消息拆分成多个部分
            parts = message.content.split(' ')

            if len(parts) < 2:
                await message.channel.send('请提供 GitHub ID')
            else:
                github_id = parts[1]  # 获取参数 github_id
                discord_id = message.author.id # 获取 discord_id
                update_github_id(discord_id, github_id)
                await message.channel.send(f'绑定成功，您绑定的 GitHub ID 是 {github_id}')
            pass

        # task: 查询所有 Open Issue
        elif command == 'task':
            # 处理 $task 命令
            # 获取仓库的名称
            repo_owner = 'SwiftGGTeam'
            repo_name = 'the-swift-programming-language-in-chinese'
            
            # 调用 GitHub API 获取仓库的所有 open issue
            response = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues?state=open")
            
            # 检查 API 响应状态码
            if response.status_code == 200:
                issues = response.json()
                # 对获取到的 issue 进行处理并以美观的样式发送出去
                await send_issues(message.channel, issues)
            else:
                await message.channel.send(f'获取任务列表失败：{response.json()}')
            pass

        # claim: 领取某 Issue
        #   - 单独给申请者发送通知消息，告知任务领取状态，如果领取成功发送仓库权限邀请消息，以及对应的 issue 链接。
        #   - 通知 issue 作者
        elif command.startswith('claim'):
            # 处理 $claim 命令

            discord_id = message.author.id # 获取 discord_id
            github_id = get_github_id(discord_id)

            if github_id:
                
                # 使用空格将消息拆分成多个部分
                parts = message.content.split(' ')

                if len(parts) < 2:
                    await message.channel.send('请提供任务 ID')
                else:
                    issue_id = parts[1]  # 获取参数 issue_id
                    
                    # 指定仓库信息
                    repo_owner = 'SwiftGGTeam'
                    repo_name = 'the-swift-programming-language-in-chinese'
                    issue_number = issue_id

                    # 指定 GitHub 用户登录名
                    assignee_login = github_id

                    # 读取 GitHub 开发者 Token
                    gh_token = os.getenv('GH_TOKEN')

                    # 构建 API 请求 URL
                    url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}/assignees'

                    # 构建请求头
                    headers = {
                        'Accept': 'application/vnd.github.v3+json',
                        'Authorization': f'token {GH_TOKEN}'
                    }

                    # 构建请求体
                    data = {
                        'assignees': [assignee_login]
                    }

                    # 发送请求
                    response = requests.post(url, headers=headers, json=data)

                    # 检查请求是否成功
                    if response.status_code == 201:
                        await message.channel.send(f'领取任务 {issue_number} 成功')
                    else:
                        await message.channel.send(f'任务领取失败：{response.json()}')
                    pass
                pass
                    
            else:
                await message.channel.send('您尚未绑定 GitHub ID，请执行 bind [github_id] 命令进行绑定')
            pass
        else:
            # 如果命令不是这些预定义的命令
            await message.channel.send('unknown!')
            pass

client.run(os.getenv('TOKEN'))
