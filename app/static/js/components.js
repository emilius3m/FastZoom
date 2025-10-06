document.addEventListener("alpine:init", () => {
  Alpine.data("register", () => ({
    message: "",
    showUsernameError: false,
    showRepeatPasswordError: false,
    showPasswordError: false,
    showPassword: false,
    showSubmitButton: false,
    showServerError: false,
    username: "",
    password: "",
    repeatPassword: "",
    emailPattern: /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/,
    passwordPattern: /^(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*]).{8,}$/,
    checkUsername() {
      if (!this.username) {
        this.showUsernameError = false;
      } else if (!this.emailPattern.test(this.username)) {
        this.showUsernameError = true;
        this.showPassword = false;
      } else {
        this.showUsernameError = false;
        this.showPassword = true;
      }
    },
    passwordsMatch() {
      if (!this.repeatPassword) {
        this.showRepeatPasswordError = false;
        this.showSubmitButton = true;
      } else if (this.password !== this.repeatPassword) {
        this.showRepeatPasswordError = true;
      } else {
        this.showRepeatPasswordError = false;
        this.showSubmitButton = false;
      }
    },
    validatePassword() {
      if (!this.password) {
        this.showPasswordError = false;
      } else if (!this.passwordPattern.test(this.password)) {
        this.showPasswordError = true;
      } else {
        this.showPasswordError = false;
      }
    },
    disableButton() {
      this.showSubmitButton = true;
    },
    checkServerError() {
      if (this.showServerError) {
        setTimeout(() => {
          this.showServerError = false;
        }, 3000);
      }
    },
    async registerUser() {
      if (!this.username || !this.password || !this.repeatPassword) {
        alert("Please fill in all fields");
        return;
      }
      if (this.password !== this.repeatPassword) {
        alert("Passwords do not match");
        return;
      }
      const formData = {
        email: this.username,
        password: this.password,
      };
      try {
        const response = await fetch("/auth/register", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(formData),
        });
        if (response.status === 201) {
          this.message = "User created successfully";
          this.showServerError = true;
          setTimeout(() => {
            window.location.href = "/";
          }, 1000);
        } else if (response.status === 400) {
          this.message = "User already exists";
          this.showServerError = true;
        }
      } catch (error) {
        console.error("Error:", error);
      }
    },
  }));
});

document.addEventListener("alpine:init", () => {
  // Alpine component to control the login form and other attributes for login page
  Alpine.data("login", () => ({
    username: "",
    password: "",
    message: "",
    showError: false,
    showUsernameError: false,
    showPasswordDiv: false,
    showInputButton: false,
    csrfToken: "",

    checkLoginUsername() {
      const emailPattern = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
      if (this.username === "") {
        this.showUsernameError = true;
      } else if (!emailPattern.test(this.username)) {
        this.showUsernameError = true;
      } else {
        this.showUsernameError = false;
        this.showPasswordDiv = true;
      }
    },

    allocateCSRFToken(value) {
      this.csrfToken = value;
    },
    setCookie() {
      const formData = new URLSearchParams();
      formData.append("grant_type", "password");
      formData.append("username", this.username);
      formData.append("email", this.username);
      formData.append("password", this.password);
      formData.append("scope", "");
      formData.append("client_id", "");
      formData.append("client_secret", "");

      fetch("/auth/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRF-Token": this.csrfToken,
        },
        body: formData,
      })
        .then((response) => {

          console.log("Response status:", response.status);
          console.log("Response headers:", response.headers);
          
          if (response.status === 204) {

            // Successful login, navigate to /dashboard
            console.log("Login successful, redirecting...");

            // Test che il cookie sia settato
            console.log("Document cookies:", document.cookie);

            // Store authentication token for WebSocket and API calls
            // Since we're using cookie-based auth, we'll use a placeholder
            // In a real implementation, you might want to extract token from response
            localStorage.setItem('access_token', 'authenticated'); // Placeholder token

            window.location.href = "/dashboard";

          } else if (response.status === 400) {
            // Incorrect username or password
            this.message = "Incorrect username or password";
            this.showError = true;
            return response.text();
          }
        })
        .then((errorMessage) => {
          if (errorMessage) {
            console.log(errorMessage);
          }
        });
    },
  }));
});

// Store pending alerts during page transitions
window.pendingAlerts = [];

// Handle page load events
document.addEventListener("DOMContentLoaded", function () {
  // Check for pending alerts from page transitions
  while (window.pendingAlerts && window.pendingAlerts.length > 0) {
    const alertData = window.pendingAlerts.pop();
    showAlertMessage(alertData);
  }
});

// Handle custom showAlert events
document.body.addEventListener("showAlert", function (evt) {
  try {
    // Store alert for processing after page load
    if (!window.pendingAlerts) {
      window.pendingAlerts = [];
    }
    window.pendingAlerts.push(evt.detail);
  } catch (error) {
    console.error("Error handling showAlert:", error);
  }
});

function showAlertMessage(alertData) {
  // Find component by ID
  const component = document.getElementById(alertData.source);

  if (!component) {
    console.warn(`No element with id '${alertData.source}' found`);
    return;
  }

  // Try to get Alpine.js data if available
  try {
    const data = Alpine.mergeProxies(component._x_dataStack);

    setTimeout(function () {
      if (alertData.type === "updated") {
        data.isUpdated = true;
        data.message = alertData.message;
      } else if (alertData.type === "added") {
        data.isAdded = true;
        data.message = alertData.message;
      } else if (alertData.type === "deleted") {
        data.isDeleted = true;
        data.message = alertData.message;
      }
    }, 1000);
  } catch (error) {
    console.warn("Could not access Alpine.js data:", error);
  }
}

// Sidebar toggle functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing sidebar...');
    
    // Ensure Flowbite is available
    if (typeof window.initFlowbite === 'function') {
        window.initFlowbite();
        console.log('Flowbite initialized');
    }
    
    // Manual sidebar toggle as fallback
    const sidebarToggle = document.querySelector('[data-drawer-toggle="logo-sidebar"]');
    const sidebar = document.getElementById('logo-sidebar');
    
    if (sidebarToggle && sidebar) {
        console.log('Sidebar elements found, adding manual toggle');
        
        sidebarToggle.addEventListener('click', function() {
            console.log('Sidebar toggle clicked');
            sidebar.classList.toggle('-translate-x-full');
        });
        
        // Close sidebar when clicking outside (on mobile)
        document.addEventListener('click', function(event) {
            const isClickInsideSidebar = sidebar.contains(event.target);
            const isToggleButton = sidebarToggle.contains(event.target);
            
            if (!isClickInsideSidebar && !isToggleButton && !sidebar.classList.contains('-translate-x-full')) {
                sidebar.classList.add('-translate-x-full');
            }
        });
        
        // Handle ESC key to close sidebar
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape' && !sidebar.classList.contains('-translate-x-full')) {
                sidebar.classList.add('-translate-x-full');
            }
        });
    } else {
        console.error('Sidebar toggle elements not found:', {
            sidebarToggle: !!sidebarToggle,
            sidebar: !!sidebar
        });
    }
});
