/**
 * 用户隔离的本地存储管理器
 */
class UserStorage {
    constructor(userId) {
        this.userId = userId;
        this.prefix = `vet_user_${userId}_`;
    }

    // 生成带用户前缀的存储键
    getKey(key) {
        return `${this.prefix}${key}`;
    }

    // 设置数据
    setItem(key, value) {
        try {
            const serializedValue = typeof value === 'string' ? value : JSON.stringify(value);
            localStorage.setItem(this.getKey(key), serializedValue);
            return true;
        } catch (error) {
            console.error('存储数据失败:', error);
            return false;
        }
    }

    // 获取数据
    getItem(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(this.getKey(key));
            if (item === null) return defaultValue;
            
            // 尝试解析JSON，如果失败则返回原始字符串
            try {
                return JSON.parse(item);
            } catch {
                return item;
            }
        } catch (error) {
            console.error('读取数据失败:', error);
            return defaultValue;
        }
    }

    // 删除数据
    removeItem(key) {
        try {
            localStorage.removeItem(this.getKey(key));
            return true;
        } catch (error) {
            console.error('删除数据失败:', error);
            return false;
        }
    }

    // 清空当前用户的所有数据
    clearUserData() {
        try {
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith(this.prefix)) {
                    keysToRemove.push(key);
                }
            }
            
            keysToRemove.forEach(key => localStorage.removeItem(key));
            console.log(`已清空用户 ${this.userId} 的所有本地数据`);
            return true;
        } catch (error) {
            console.error('清空用户数据失败:', error);
            return false;
        }
    }

    // 获取当前用户数据大小（估算）
    getDataSize() {
        let totalSize = 0;
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith(this.prefix)) {
                const value = localStorage.getItem(key);
                totalSize += key.length + (value ? value.length : 0);
            }
        }
        return totalSize;
    }

    // 列出当前用户的所有存储键
    getUserKeys() {
        const userKeys = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith(this.prefix)) {
                userKeys.push(key.replace(this.prefix, ''));
            }
        }
        return userKeys;
    }

    // 导出用户数据
    exportUserData() {
        const userData = {};
        const userKeys = this.getUserKeys();
        
        userKeys.forEach(key => {
            userData[key] = this.getItem(key);
        });
        
        return {
            userId: this.userId,
            exportTime: new Date().toISOString(),
            data: userData
        };
    }

    // 导入用户数据
    importUserData(exportedData) {
        if (exportedData.userId !== this.userId) {
            console.warn('用户ID不匹配，请确认数据来源');
            return false;
        }
        
        try {
            Object.entries(exportedData.data).forEach(([key, value]) => {
                this.setItem(key, value);
            });
            console.log('用户数据导入成功');
            return true;
        } catch (error) {
            console.error('导入用户数据失败:', error);
            return false;
        }
    }
}

// 全局用户存储管理器
window.UserStorage = UserStorage;
