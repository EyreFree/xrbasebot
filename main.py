import os
from dotenv import load_dotenv
import discord
import sqlite3
import requests
import re

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

def get_discord_id(github_id):
    conn = sqlite3.connect('user_accounts.db')
    c = conn.cursor()

    # 查询目标用户的记录，并返回对应的 discord_id
    c.execute('SELECT user_id FROM accounts WHERE github_id = ?', (github_id,))
    result = c.fetchone()

    conn.close()

    if result:
        return result[0]
    else:
        return None

def send_issues(channel, issues):
    target_issues = []
    for issue in issues:
        if "/pull" not in issue['html_url']:
            target_issues.append(issue)

    if len(target_issues) > 0:
        list_string = ''
        for issue in target_issues:
            number = issue['number']
            title = issue['title']
            url = issue['html_url']
            body = issue.get('body')
            if not body:
                body = '无描述'
            author = issue['user']['login']
            
            list_string += f"#{number} {title}\n"

        return f"任务列表：\n{list_string}"
    else:
        return '目前没有待处理的任务'

def send_issue_detail(channel, issue):
    if "/pull" in issue['html_url']:
        return '这不是一个合法任务'
    else:
        number = issue['number']
        title = issue['title']
        url = issue['html_url']
        body = issue.get('body')
        if not body:
            body = '无描述'
        author = issue['user']['login']
        
        msg = f"**任务**：{number}\n**标题**：{title}\n**作者**：{author}\n**描述**：{body}\n**URL**：{url}\n"
        msg = re.sub(r"(https?://[^\s]+)", r"<\1>", msg)

        return msg

def get_assigned_issue_ids(issues, github_id):
    assigned_issue_ids = []
    for issue in issues:
        if "/pull" not in issue['html_url']:
            assignees = issue.get('assignees', [])
            assignee_logins = [assignee['login'].lower() for assignee in assignees]
            if github_id.lower() in assignee_logins:
                issue_id = issue['number']
                assigned_issue_ids.append(issue_id)
    return sorted(assigned_issue_ids)

def add_collaborator(repo_owner, repo_name, github_id):
    return ''

    # 下面的代码需求有点问题，待讨论，先留着

    # 替换为你的 GitHub token
    token = os.getenv('GH_TOKEN')

    # 构建 API 请求的 URL
    url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/collaborators/{github_id}'

    # 设置请求头，包括身份验证 token
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'permission': 'triage',
    }

    # 发送 PUT 请求将用户添加为 Collaborator
    response = requests.put(url, headers=headers)

    return response.text

    # 检查响应状态码
    if response.status_code == 201:
        return f"已将您添加为协作者，仓库权限邀请：https://github.com/{repo_owner}/{repo_name}/invitations/new?invitee={github_id}"
    else:
        return f"在添加您为仓库协作者时失败，请联系管理员，错误消息：{response.json()['message']}"
        
@client.event
async def on_ready():
    create_table()
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    msg_return = ''

    # 无视机器人自己的消息
    if message.author == client.user:
        return

    # 调试用：看看这条消息
    # await message.channel.send(message)

    # 是否为私聊
    is_private_chat = isinstance(message.channel, discord.DMChannel)

    if message.content.startswith('$'):
        command = message.content[1:]  # 获取命令名，去除前缀 $

        # info: 列出我的所有信息
        #   - GitHub 账号
        #   - 已领取的任务(根据 GitHub)
        if command == 'help':
            help_msg = [
                '指令列表:',
                '$info：列出我的所有账号信息',
                '$bind [github_id]：绑定 GitHub 账号',
                '$tasks：列出全部可领取的任务，Issue 序号即为任务 ID',
                '$task [task_id]：查询任务详情，Issue 序号即为任务 ID',
                '$claim [task_id]：领取某任务，Issue 序号即为任务 ID'
            ]
            msg_return = "\n".join(map(str, help_msg))
            pass

        # info: 列出我的所有信息
        #   - GitHub 账号
        #   - 已领取的任务(根据 GitHub)
        elif command == 'info':
            # 处理 $info 命令
            
            # 根据 discord_id 获取对应的 github_id
            discord_id = message.author.id
            github_id = get_github_id(discord_id)

            if github_id:
                info_msg = f'您绑定的 GitHub ID 是：{github_id}\n'

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
                        info_msg += f'指派给您的任务 ID 为：{", ".join(map(str, assigned_issue_ids))}'
                    else:
                        info_msg += f'目前没有找到指派给您的任务'
                else:
                    info_msg += f"获取任务列表失败：{response.json()['message']}"
                    
                msg_return = info_msg
            else:
                msg_return = '您尚未绑定 GitHub ID，请执行 bind [github_id] 命令进行绑定'
            pass

        # bind: 绑定 GitHub 账号
        elif command.startswith('bind'):
            # 处理 $bind 命令
            
            # 使用空格将消息拆分成多个部分
            parts = message.content.split(' ')

            if len(parts) < 2:
                msg_return = '请提供 GitHub ID'
            else:
                github_id = parts[1]  # 获取参数 github_id
                discord_id = message.author.id # 获取 discord_id
                update_github_id(discord_id, github_id)
                msg_return = f'绑定成功，您绑定的 GitHub ID 是 {github_id}'
            pass

        # task: 查询所有 Open Issue
        elif command == 'tasks':
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
                msg_return = send_issues(message.channel, issues)
            else:
                msg_return = f"获取任务列表失败：{response.json()['message']}"
            pass

        # bind: 绑定 GitHub 账号
        elif command.startswith('task'):
            # 处理 $bind 命令
            
            # 使用空格将消息拆分成多个部分
            parts = message.content.split(' ')

            if len(parts) < 2:
                msg_return = '请提供任务 ID'
            else:
                issue_number = parts[1]  # 获取参数 github_id

                # 获取仓库的名称
                repo_owner = 'SwiftGGTeam'
                repo_name = 'the-swift-programming-language-in-chinese'
                
                # 调用 GitHub API 获取仓库的指定 issue
                response = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}")
                
                # 检查 API 响应状态码
                if response.status_code == 200:
                    issue_detail = response.json()
                    # 对获取到的 issue 进行处理并以美观的样式发送出去
                    msg_return = send_issue_detail(message.channel, issue_detail)
                else:
                    msg_return = f"获取任务详情失败：{response.json()['message']}"
                pass
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
                    msg_return = '请提供任务 ID'
                else:
                    issue_id = parts[1]  # 获取参数 issue_id
                    
                    # 指定仓库信息
                    repo_owner = 'SwiftGGTeam'
                    repo_name = 'the-swift-programming-language-in-chinese'
                    issue_number = issue_id

                    # 调用 GitHub API 获取仓库的指定 issue
                    response = requests.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}")
                    
                    # 检查 API 响应状态码
                    if response.status_code == 200:
                        issue_detail = response.json()
                        assignees = issue_detail.get('assignees', [])
                        
                        if len(assignees) != 0:
                            assignee_logins = [assignee['login'].lower() for assignee in assignees]
                            if github_id.lower() in assignee_logins:
                                msg_return = f'您已领取该任务 {issue_number}'
                            else:
                                msg_return = f'该任务 {issue_number} 已被其他用户领取'
                        elif "/pull" in issue_detail['html_url']:
                            msg_return = '这不是一个合法任务'
                        elif 'open' != issue_detail['state']:
                            msg_return = '这不是一个活跃任务'
                        else:
                            # 指定 GitHub 用户登录名
                            assignee_login = github_id

                            # 读取 GitHub 开发者 Token
                            gh_token = os.getenv('GH_TOKEN')

                            # 构建 API 请求 URL
                            url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}/assignees'

                            # 构建请求头
                            headers = {
                                'Accept': 'application/vnd.github.v3+json',
                                'Authorization': f'token {gh_token}'
                            }

                            # 构建请求体
                            data = {
                                'assignees': [assignee_login]
                            }

                            # 发送请求
                            response = requests.post(url, headers=headers, json=data)

                            # 检查请求是否成功
                            if response.status_code == 201:
                                msg_return = f'领取任务 {issue_number} 成功'

                                # 领取任务成功单独私信，获取要私信的用户
                                target_user = client.get_user(discord_id)
                                add_collaborator_result = add_collaborator(repo_owner, repo_name, github_id)
                                pri_msg = f"任务链接：<https://github.com/{repo_owner}/{repo_name}/issues/{issue_number}>\n{add_collaborator_result}"
                                if is_private_chat == False:
                                    pri_msg = f'{msg_return}\n{pri_msg}'
                                await target_user.send(pri_msg)

                                # 领取任务成功单独私信，获取要私信的用户
                                creator_github_id = issue_detail['user']['login']
                                creator_discord_id = get_discord_id(creator_github_id)
                                if creator_discord_id:
                                    target_creator = client.get_user(creator_discord_id)
                                    pri_creator_msg = f"您提交的 Issue 已被认领\n任务链接：<https://github.com/{repo_owner}/{repo_name}/issues/{issue_number}>"
                                    await target_user.send(pri_creator_msg)
                                pass
                            else:
                                msg_return = f"任务领取失败：{response.json()['message']}"
                            pass
                        pass
                    else:
                        msg_return = f"获取任务详情失败：{response.json()['message']}"
                    pass
                pass
                    
            else:
                msg_return = '您尚未绑定 GitHub ID，请执行 bind [github_id] 命令进行绑定'
            pass
        else:
            # 如果命令不是这些预定义的命令
            msg_return = '无效命令，请执行 $help 查看帮助'
            pass

    if len(msg_return) != 0:
        msg_content = msg_return
        if is_private_chat:
            msg_content = msg_return
        else:
            msg_content = f"<@{message.author.id}> {msg_return}"
        await message.channel.send(msg_content)


client.run(os.getenv('TOKEN'))
