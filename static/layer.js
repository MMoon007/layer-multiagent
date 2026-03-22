let currentMode = "workflow";
let currentTaskId = null;
let currentUserId = localStorage.getItem("currentUserId") || null;
let userStorage = null;
let taskManager = null;
let isAutoLoginInProgress = false;

const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const newTaskBtn = document.getElementById("new-task-btn");
const modeOptions = document.querySelectorAll(".mode-option");
const modeIcon = document.getElementById("mode-icon");
const modeName = document.getElementById("mode-name");
const userIdModal = document.getElementById("user-id-modal");
const userIdInput = document.getElementById("user-id-input");
const userIdConfirm = document.getElementById("user-id-confirm");
const clearAllTasksBtn = document.getElementById("clear-all-tasks-btn");
const userMenuBtn = document.getElementById("user-menu-btn");
const userDropdown = document.getElementById("user-dropdown");
const logoutBtn = document.getElementById("logout-btn");
const currentUserDisplay = document.getElementById("current-user-display");
const dropdownUserName = document.getElementById("dropdown-user-name");
const menuToggle = document.getElementById("menu-toggle");
const sidebar = document.querySelector(".sidebar");
const sidebarOverlay = document.querySelector(".sidebar-overlay");
const voiceBtn = document.getElementById("voice-btn");
const attachmentBtn = document.getElementById("attachment-btn");


class TaskManager {
    constructor(storage) {
        this.userStorage = storage;
        this.tasks = this.normalizeTasks(this.userStorage ? this.userStorage.getItem("legalTasks", []) : []);
        this.render();
    }

    normalizeTasks(tasks) {
        if (!Array.isArray(tasks)) {
            return [];
        }

        return tasks.map((task) => ({
            ...task,
            mode: "workflow",
            title: task?.title || "多智能体工作流",
            messages: Array.isArray(task?.messages) ? task.messages : [],
            createdAt: task?.createdAt || new Date().toISOString(),
            updatedAt: task?.updatedAt || new Date().toISOString(),
        }));
    }

    createTask() {
        const task = {
            id: Date.now().toString(),
            mode: "workflow",
            title: "多智能体工作流",
            messages: [],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        };

        this.tasks.unshift(task);
        this.saveToStorage();
        this.render();
        return task;
    }

    addMessage(taskId, role, content) {
        const task = this.getTask(taskId);
        if (!task) {
            return;
        }

        task.messages.push({ role, content, timestamp: new Date().toISOString() });
        task.updatedAt = new Date().toISOString();

        if (role === "user" && task.messages.filter((message) => message.role === "user").length === 1) {
            task.title = content.slice(0, 30) + (content.length > 30 ? "..." : "");
        }

        this.saveToStorage();
        this.render();
    }

    getTask(taskId) {
        return this.tasks.find((task) => task.id === taskId);
    }

    deleteTask(taskId) {
        const wasCurrent = currentTaskId === taskId;
        this.tasks = this.tasks.filter((task) => task.id !== taskId);
        this.saveToStorage();
        this.render();

        if (!wasCurrent) {
            return;
        }

        if (this.tasks.length > 0) {
            this.switchToTask(this.tasks[0].id);
        } else {
            createNewTask();
        }
    }

    clearAllTasks() {
        this.tasks = [];
        currentTaskId = null;
        this.saveToStorage();
        this.render();
        chatWindow.innerHTML = "";
        createNewTask();
    }

    saveToStorage() {
        if (!this.userStorage) {
            return;
        }

        this.userStorage.setItem("legalTasks", this.tasks);
        if (currentTaskId) {
            this.userStorage.setItem("currentTaskId", currentTaskId);
        }
    }

    render() {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
        const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

        const todayTasks = [];
        const yesterdayTasks = [];
        const weekTasks = [];

        this.tasks.forEach((task) => {
            const taskDate = new Date(task.updatedAt);
            const taskDay = new Date(taskDate.getFullYear(), taskDate.getMonth(), taskDate.getDate());

            if (taskDay.getTime() === today.getTime()) {
                todayTasks.push(task);
            } else if (taskDay.getTime() === yesterday.getTime()) {
                yesterdayTasks.push(task);
            } else if (taskDate >= weekAgo) {
                weekTasks.push(task);
            }
        });

        this.renderTaskSection("today-tasks", todayTasks);
        this.renderTaskSection("yesterday-tasks", yesterdayTasks);
        this.renderTaskSection("week-tasks", weekTasks);
    }

    renderTaskSection(containerId, tasks) {
        const container = document.getElementById(containerId);
        if (!container) {
            return;
        }

        container.innerHTML = "";

        tasks.forEach((task) => {
            const taskElement = document.createElement("div");
            taskElement.className = `task-item ${task.id === currentTaskId ? "active" : ""}`;
            taskElement.innerHTML = `
                <i class="fas fa-diagram-project"></i>
                <span class="task-title">${task.title}</span>
                <button type="button" class="task-delete-btn" title="删除任务" aria-label="删除任务">
                    <i class="fas fa-trash"></i>
                </button>
            `;

            taskElement.addEventListener("click", () => {
                this.switchToTask(task.id);
            });

            const deleteBtn = taskElement.querySelector(".task-delete-btn");
            deleteBtn.addEventListener("click", (event) => {
                event.stopPropagation();
                if (window.confirm("确认删除该任务？此操作不可恢复。")) {
                    this.deleteTask(task.id);
                }
            });

            container.appendChild(taskElement);
        });
    }

    switchToTask(taskId) {
        const task = this.getTask(taskId);
        if (!task) {
            return;
        }

        currentTaskId = taskId;
        currentMode = "workflow";
        this.updateModeUI();
        this.render();
        this.loadTaskMessages(task);

        if (this.userStorage) {
            this.userStorage.setItem("currentTaskId", currentTaskId);
        }
    }

    updateModeUI() {
        modeIcon.className = "fas fa-diagram-project";
        modeName.textContent = "多智能体工作流";
        modeOptions.forEach((option) => {
            option.classList.toggle("active", option.dataset.mode === "workflow");
        });
    }

    loadTaskMessages(task) {
        chatWindow.innerHTML = "";
        if (task.messages.length === 0) {
            this.showWelcomeMessage();
            return;
        }

        task.messages.forEach((message) => {
            this.appendMessage(message.role, message.content);
        });
    }

    showWelcomeMessage() {
        this.appendMessage(
            "ai",
            "您好，欢迎来到智能法律咨询助手。我能帮助您解答法律问题、提供法律建议，或者协助您完成一些法律相关的任务。请随时告诉我您需要什么帮助！"
        );
    }

    appendMessage(role, content) {
        const messageDiv = document.createElement("div");
        messageDiv.className = `message ${role}`;

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.innerHTML = role === "user" ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

        const messageContent = document.createElement("div");
        messageContent.className = "message-content";
        if (role === "ai") {
            messageContent.innerHTML = this.renderMarkdown(content);
        } else {
            messageContent.textContent = content;
        }

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    renderMarkdown(mdText) {
        if (!mdText) {
            return "";
        }

        try {
            const md = window.markdownit({
                html: false,
                linkify: true,
                typographer: true,
                breaks: true,
            });
            const dirty = md.render(mdText);
            const clean = window.DOMPurify
                ? window.DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true } })
                : dirty;
            return `<div class="md">${clean}</div>`;
        } catch (error) {
            console.error("Markdown 渲染失败，回退纯文本:", error);
            return `<div class="md"><pre>${mdText}</pre></div>`;
        }
    }
}


function clearUIForLogin() {
    chatWindow.innerHTML = "";
    currentUserDisplay.textContent = "";
    dropdownUserName.textContent = "";
    document.getElementById("today-tasks").innerHTML = "";
    document.getElementById("yesterday-tasks").innerHTML = "";
    document.getElementById("week-tasks").innerHTML = "";
    currentMode = "workflow";
    modeIcon.className = "fas fa-diagram-project";
    modeName.textContent = "多智能体工作流";
    modeOptions.forEach((option) => {
        option.classList.toggle("active", option.dataset.mode === "workflow");
    });
}

function showUserIdModal() {
    if (isAutoLoginInProgress) {
        return;
    }

    clearUIForLogin();
    userIdModal.classList.remove("hidden");
    userIdInput.focus();
}

function hideUserIdModal() {
    userIdModal.classList.add("hidden");
}

function updateUserDisplay() {
    if (!currentUserId) {
        return;
    }

    currentUserDisplay.textContent =
        currentUserId.length > 8 ? `${currentUserId.substring(0, 8)}...` : currentUserId;
    dropdownUserName.textContent = currentUserId;
}

function setUserId(userId) {
    currentUserId = userId;
    localStorage.setItem("currentUserId", userId);
    userStorage = new UserStorage(userId);
    taskManager = new TaskManager(userStorage);
    updateUserDisplay();
}

function showAutoLoginMessage(userId) {
    const toast = document.createElement("div");
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(135deg, #4CAF50, #45a049);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        font-size: 14px;
        opacity: 0;
        transition: opacity 0.3s ease;
    `;
    toast.textContent = `欢迎回来，${userId}`;

    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "1";
    }, 100);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3000);
}

function logout() {
    localStorage.removeItem("currentUserId");
    currentUserId = null;
    userStorage = null;
    taskManager = null;
    showUserIdModal();
}

function initializeControls() {
    if (voiceBtn) {
        voiceBtn.addEventListener("click", () => {
            showToast("语音输入功能正在开发中...", "info");
        });
    }

    if (attachmentBtn) {
        attachmentBtn.addEventListener("click", () => {
            showToast("附件功能正在开发中...", "info");
        });
    }
}

function initializeAppComponents() {
    currentTaskId = userStorage.getItem("currentTaskId");

    if (currentTaskId) {
        const task = taskManager.getTask(currentTaskId);
        if (task) {
            taskManager.switchToTask(currentTaskId);
        } else {
            createNewTask();
        }
    } else {
        createNewTask();
    }

    initializeControls();
}

function initializeApp() {
    if (!userStorage || !taskManager) {
        if (!currentUserId) {
            showUserIdModal();
            return;
        }
        setUserId(currentUserId);
    }

    initializeAppComponents();
}

function createNewTask() {
    if (!taskManager) {
        if (!currentUserId) {
            console.error("无法创建任务: 用户未登录");
            return;
        }
        setUserId(currentUserId);
    }

    const task = taskManager.createTask();
    currentTaskId = task.id;
    currentMode = "workflow";
    taskManager.switchToTask(currentTaskId);
}

function toggleSidebar() {
    sidebar.classList.toggle("open");
    sidebarOverlay.classList.toggle("active");

    const icon = menuToggle.querySelector("i");
    icon.className = sidebar.classList.contains("open") ? "fas fa-times" : "fas fa-bars";
}

function closeSidebar() {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("active");
    const icon = menuToggle.querySelector("i");
    if (icon) {
        icon.className = "fas fa-bars";
    }
}

function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    Object.assign(toast.style, {
        position: "fixed",
        top: "20px",
        right: "20px",
        background: type === "success" ? "#4CAF50" : "#2196F3",
        color: "white",
        padding: "12px 20px",
        borderRadius: "6px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        zIndex: "10000",
        fontSize: "14px",
        fontWeight: "500",
        opacity: "0",
        transform: "translateY(-10px)",
        transition: "all 0.3s ease",
    });

    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translateY(0)";
    }, 10);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-10px)";
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3000);
}


document.addEventListener("DOMContentLoaded", () => {
    const storedUserId = localStorage.getItem("currentUserId");
    if (!storedUserId || storedUserId.trim() === "") {
        showUserIdModal();
        return;
    }

    isAutoLoginInProgress = true;
    currentUserId = storedUserId;
    setUserId(currentUserId);
    initializeAppComponents();
    showAutoLoginMessage(currentUserId);
    hideUserIdModal();
    isAutoLoginInProgress = false;
});

newTaskBtn.addEventListener("click", () => {
    createNewTask();
});

modeOptions.forEach((option) => {
    option.addEventListener("click", () => {
        option.classList.add("active");
    });
});

userIdConfirm.addEventListener("click", () => {
    const userId = userIdInput.value.trim();
    if (!userId) {
        alert("请输入用户 ID");
        return;
    }

    setUserId(userId);
    hideUserIdModal();
    initializeApp();
});

userIdInput.addEventListener("keypress", (event) => {
    if (event.key === "Enter") {
        userIdConfirm.click();
    }
});

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = userInput.value.trim();
    if (!text) {
        return;
    }

    if (!currentTaskId || !taskManager) {
        createNewTask();
    }

    taskManager.addMessage(currentTaskId, "user", text);
    taskManager.appendMessage("user", text);
    userInput.value = "";

    try {
        const response = await fetch("/send_message_stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                mode: "workflow",
                task_id: currentTaskId,
                user_id: currentUserId,
            }),
        });

        const aiMessageDiv = document.createElement("div");
        aiMessageDiv.className = "message ai";
        aiMessageDiv.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-content">
                <div class="streaming-content"></div>
                <span class="cursor"></span>
            </div>
        `;
        chatWindow.appendChild(aiMessageDiv);
        const streamingContent = aiMessageDiv.querySelector(".streaming-content");
        const cursor = aiMessageDiv.querySelector(".cursor");

        let fullResponse = "";
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }

            const chunk = decoder.decode(value);
            const lines = chunk.split("\n");

            for (const line of lines) {
                if (!line.startsWith("data: ")) {
                    continue;
                }

                try {
                    const data = JSON.parse(line.slice(6));

                    if (data.type === "clear") {
                        fullResponse = "";
                        streamingContent.innerHTML = "";
                        chatWindow.scrollTop = chatWindow.scrollHeight;
                    } else if (data.type === "token") {
                        fullResponse += data.content;
                        streamingContent.innerHTML = taskManager.renderMarkdown(fullResponse);
                        chatWindow.scrollTop = chatWindow.scrollHeight;
                    } else if (data.type === "done") {
                        cursor.remove();
                        if (!fullResponse && data.response) {
                            fullResponse = data.response;
                            streamingContent.innerHTML = taskManager.renderMarkdown(fullResponse);
                        }
                        taskManager.addMessage(currentTaskId, "ai", fullResponse);
                    } else if (data.type === "error") {
                        cursor.remove();
                        streamingContent.textContent = `抱歉，发生了错误：${data.message}`;
                    }
                } catch (error) {
                    console.error("解析 SSE 数据错误:", error, line);
                }
            }
        }
    } catch (error) {
        console.error("Error:", error);
        taskManager.appendMessage("ai", "抱歉，发生了错误，请稍后重试。");
    }
});

clearAllTasksBtn.addEventListener("click", () => {
    if (taskManager && confirm("确定要清理所有任务吗？此操作不可恢复。")) {
        taskManager.clearAllTasks();
    }
});

userMenuBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    userDropdown.classList.toggle("hidden");
});

document.addEventListener("click", (event) => {
    if (!userDropdown.contains(event.target) && !userMenuBtn.contains(event.target)) {
        userDropdown.classList.add("hidden");
    }
});

logoutBtn.addEventListener("click", () => {
    if (confirm("确定要退出登录吗？")) {
        logout();
        userDropdown.classList.add("hidden");
    }
});

document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "n") {
        event.preventDefault();
        createNewTask();
    }
});

if (menuToggle) {
    menuToggle.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleSidebar();
    });
}

if (sidebarOverlay) {
    sidebarOverlay.addEventListener("click", closeSidebar);
}

const originalSwitchToTask = TaskManager.prototype.switchToTask;
TaskManager.prototype.switchToTask = function (taskId) {
    originalSwitchToTask.call(this, taskId);
    if (window.innerWidth <= 768) {
        closeSidebar();
    }
};

let resizeTimer;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (window.innerWidth > 768) {
            sidebar.classList.remove("open");
            sidebarOverlay.classList.remove("active");
            const icon = menuToggle.querySelector("i");
            if (icon) {
                icon.className = "fas fa-bars";
            }
        }
    }, 250);
});

document.addEventListener(
    "touchmove",
    (event) => {
        if (sidebar.classList.contains("open") && !sidebar.contains(event.target)) {
            event.preventDefault();
        }
    },
    { passive: false }
);
