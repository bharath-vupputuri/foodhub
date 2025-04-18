
import logging
from flask import Flask, render_template, redirect, url_for, request, flash,jsonify,session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, HiddenField
from wtforms.validators import InputRequired, Length, Email, Regexp
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import google.generativeai as genai


GEMINI_API_KEY = "AIzaSyBkCxP-RwWc4-qqBfFvJ9HKxlBLlgN4g2w"
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask App Configuration
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class Payment(db.Model):
    __tablename__ = 'payment'
    payment_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    order_id = db.Column(db.Integer, nullable=True)  # Optional link to PlacedOrders; null until order is confirmed
    amount = db.Column(db.Float, nullable=False)  # Total payment amount
    payment_method = db.Column(db.String(50), nullable=False)  # e.g., "Credit Card", "PayPal"
    payment_status = db.Column(db.String(20), default='Pending', nullable=False)  # e.g., "Pending", "Completed", "Failed"
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', backref='payments')


class User(db.Model, UserMixin):
    __tablename__ = 'user'  # Ensure correct table name
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    



# New PlacedOrders model
class PlacedOrders(db.Model):
    __tablename__ = 'placed_orders'
    order_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('menu_item.item_id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships (optional, for easier querying)
    user = db.relationship('User', backref='placed_orders')
    item = db.relationship('MenuItem', backref='order_entries')
    
    

# ✅ MenuItem Model (Table name is `menu_item`)
class MenuItem(db.Model):
    __tablename__ = 'menu_item'  # Ensure correct table name
    item_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    group_type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(255))

# ✅ Cart Model (Fixed Foreign Keys & Table Name Issues)
class Cart(db.Model):
    __tablename__ = 'cart'
    cart_id = db.Column(db.Integer, primary_key=True)
    
    # ✅ Corrected Foreign Key References
    id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('menu_item.item_id', ondelete='CASCADE'), nullable=False)
    
    quantity = db.Column(db.Integer, default=1, nullable=False)
    added_at = db.Column(db.DateTime, server_default=db.func.now())

    # Relationships
    user = db.relationship('User', backref='cart_items')
    item = db.relationship('MenuItem', backref='cart_entries')

    # ✅ Fixed Unique Constraint (Ensure correct column names)
    __table_args__ = (db.UniqueConstraint('id', 'item_id', name='unique_user_item'),)

# Registration Form
class RegisterForm(FlaskForm):
    name = StringField('Full Name', validators=[InputRequired(), Length(min=4, max=50)])
    email = StringField('Email', validators=[InputRequired(), Email(), Length(max=100)])
    phone = StringField('Phone Number', validators=[
        InputRequired(), Length(min=10, max=15), Regexp(r'^\d+$', message="Phone number must contain only digits.")
    ])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6, max=80)])
    role = HiddenField('Role', validators=[InputRequired()])
    submit = SubmitField('Register')


# Login Form
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[InputRequired(), Email(), Length(max=100)])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6, max=80)])
    submit = SubmitField('Login')


# Load User for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    logger.debug(f'Loading user with ID: {user_id}')
    return User.query.get(int(user_id))


@app.route('/')
def landing():
    return render_template('landing.html')


# Register Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        new_user = User(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            password=hashed_password,
            role=form.role.data
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            logger.info(f'User {new_user.email} registered successfully')
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error registering user: {e}')
            flash('Email or phone number already exists or another error occurred.', 'danger')
    else:
        logger.debug(f'Form validation failed with errors: {form.errors}')
        flash('Please check your input and try again.', 'danger')

    return render_template('register.html', form=form)


# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user)

            logger.debug(f"User {user.email} logged in with role: {user.role}")

            if user.role == 'restaurant':
                return redirect(url_for('restaurant_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('login.html', form=form)


# Dashboard Route (Protected)
@app.route('/dashboard')
@login_required
def dashboard():
    menu_items = MenuItem.query.all()
    logger.debug(f'User {current_user.email} accessed dashboard')
    return render_template('dashboard.html',menu_items=menu_items)

#restaurant_dashboard Route (Protected)
@app.route('/restaurant_dashboard')
@login_required
def restaurant_dashboard():
    return render_template('restaurant_dashboard.html')

@app.route('/aichatboard')
@login_required
def aichatboard():
    return render_template('aichatboard.html')
    
# Cart Route (Protected)
@app.route('/cart')
@login_required
def cart():
    cart_items = Cart.query.filter_by(id=current_user.id).all()
    # Calculate total amount, default to 0.00 if cart is empty
    total_amount = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items) if cart_items else 0.00
    return render_template('cart.html', cart_items=cart_items, total_amount=total_amount)


# Delete Address Route (Protected)
@app.route('/del_address')
@login_required
def del_address():
    logger.debug(f'User {current_user.email} accessed del_address')
    return render_template('del_address.html',user=current_user)



@app.route('/delivery_tracking')
@login_required
def delivery_tracking():
    logger.debug(f'User {current_user.email} accessed delivery_tracking')
    return render_template('delivery_tracking.html',user=current_user)

@app.route('/restaurant_menu')
def restaurant_menu():
    menu_items = MenuItem.query.all()
    return render_template('restaurant_menu.html', menu_items=menu_items)

# Add item to cart
@app.route('/')
def index():
    return render_template('index.html')

from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from flask_sqlalchemy import SQLAlchemy

# Assuming app and db are already initialized as in the provided code

@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
@login_required
def add_to_cart(item_id):
    user_id = current_user.id
    
    # Check if the item is already in the user's cart
    cart_item = Cart.query.filter_by(id=user_id, item_id=item_id).first()
    
    if cart_item:
        # If item exists, increment the quantity
        cart_item.quantity += 1
    else:
        # If item doesn't exist, create a new cart entry
        cart_item = Cart(id=user_id, item_id=item_id, quantity=1)
        db.session.add(cart_item)
    
    # Commit changes to the database
    db.session.commit()
    
    flash('Item added to cart successfully!', 'success')
    return redirect(url_for('cart'))

@app.route('/get_cart')
def get_cart():
    return jsonify({'cart': session.get('cart', {}), 'cart_count': sum(item['quantity'] for item in session.get('cart', {}).values())})

@app.route('/restaurant_orders')
def restaurant_orders():
    return render_template('restaurant_orders.html')

@app.route('/restaurant_review')
def restaurant_review():
    return render_template('restaurant_review.html')

@app.route('/restaurant_settings')
def restaurant_settings():
    return render_template('restaurant_settings.html')


@app.route('/restaurant_additem', methods=['GET', 'POST'])
def restaurant_additem():
    if request.method == 'POST':
        name = request.form['name']
        group_type = request.form['group']
        price = float(request.form['price'])
        image = request.form['image']

        new_item = MenuItem(name=name, group_type=group_type, price=price, image=image)
        db.session.add(new_item)
        db.session.commit()
    menu_items = MenuItem.query.all()
    return render_template('restaurant_additem.html', menu_items=menu_items)

@app.route('/restaurant_edititem/<int:item_id>', methods=['GET', 'POST'])
def restaurant_edititem(item_id):
    item = MenuItem.query.get_or_404(item_id)

    if request.method == 'POST':
        item.name = request.form['name']
        item.group_type = request.form['group']
        item.price = float(request.form['price'])
        item.image = request.form['image']

        db.session.commit()
        return redirect(url_for('restaurant_additem'))

    return render_template('edit_item.html', item=item)




@app.route('/payment', methods=['GET', 'POST'])
@login_required
def payment():
    cart_items = Cart.query.filter_by(id=current_user.id).all()
    
    if not cart_items:
        flash('Your cart is empty! Please add items before proceeding to payment.', 'warning')
        return redirect(url_for('cart'))
    
    if request.method == 'POST':
        total_amount = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items)
        payment = Payment(
            user_id=current_user.id,
            amount=total_amount,
            payment_method='Credit Card',
            payment_status='Completed'
        )
        db.session.add(payment)
        db.session.flush()
        
        for cart_item in cart_items:
            order = PlacedOrders(
                user_id=current_user.id,
                item_id=cart_item.item_id,
                quantity=cart_item.quantity
            )
            db.session.add(order)
        
        for cart_item in cart_items:
            db.session.delete(cart_item)
        
        db.session.commit()
        
        flash('Payment successful! Your order has been placed.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('payment.html', cart_items=cart_items)


@app.route('/restaurant_deleteitem/<int:item_id>')
def restaurant_deleteitem(item_id):
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('restaurant_additem'))

@app.route('/logout')
@login_required
def logout():
    logger.info(f'User {current_user.email} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))




genai.configure(api_key="AIzaSyBkCxP-RwWc4-qqBfFvJ9HKxlBLlgN4g2w")

# Configuration for the AI model
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

# Initialize the AI model
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
)

def GenerateResponse(input_text):
    """
    Generate a response from the AI model based on user input.
    """
    response = model.generate_content([
        "input: who are you",
        "output: I am an AI Agent chatbot",
        "input: What all can you do?",
        "output: I can help you with few instructions to get-rid of problems faced in this website.",
        f"input: {input_text}",
        "output: ",
    ])
    return response.text

@app.route('/chatbot')
def chatbot():
    """Serve the chatbot page."""
    return render_template('chatbot.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages and return AI responses."""
    user_message = request.form['message']
    bot_response = GenerateResponse(user_message)
    return jsonify({'response': bot_response})



@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    # Fetch cart items for the current user
    cart_items = Cart.query.filter_by(id=current_user.id).all()
    
    # Check if cart is empty
    if not cart_items:
        flash('Your cart is empty!', 'warning')  # Flash message for empty cart
        return redirect(url_for('cart'))
    
    # Transfer cart items to placed_orders
    for cart_item in cart_items:
        order = PlacedOrders(
            user_id=current_user.id,
            item_id=cart_item.item_id,
            quantity=cart_item.quantity
        )
        db.session.add(order)
    
    # Clear the cart
    for cart_item in cart_items:
        db.session.delete(cart_item)
    
    # Commit all changes to the database
    db.session.commit()
    
    # Flash success message
    flash('Order placed successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/home')
@login_required
def home():
    return render_template('home.html', user=current_user)

# Create Database Tables if They Don't Exist
if __name__ == '__main__':
    if not os.path.exists("users.db"):
        with app.app_context():
            db.create_all()
            logger.info('Database initialized successfully!')
    logger.info('Starting Flask application...')
    app.run(debug=True) 
