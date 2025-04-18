import os
import logging
from flask import Flask, render_template, redirect, url_for, request, flash,jsonify,session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, HiddenField
from wtforms.validators import InputRequired, Length, Email, Regexp
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime,timedelta
import google.generativeai as genai


GEMINI_API_KEY = "AIzaSyBkCxP-RwWc4-qqBfFvJ9HKxlBLlgN4g2w"
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask App Configuration
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://food_qrdm_user:CTko1Zh2X1NrX0pkr5N6sY9U6rX6SHLc@dpg-d00tkk24d50c73clcs50-a/food_qrdm'
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

#  Review Model
class Review(db.Model):
    __tablename__ = 'review'
    review_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('placed_orders.order_id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    review_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', backref='reviews_written')
    order = db.relationship('PlacedOrders', backref='reviews')

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
    __tablename__ = 'menu_item'
    item_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    group_type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(255))
    restaurant_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    restaurant = db.relationship('User', backref='menu_items')

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

# ... (other imports and configurations remain unchanged)
from datetime import timedelta

@app.route('/restaurant_orders')
@login_required
def restaurant_orders():
    if current_user.role != 'restaurant':
        flash('Access denied. Restaurant role required.', 'danger')
        return redirect(url_for('dashboard'))

    # Query all orders with their items and user details
    orders = PlacedOrders.query.join(User).join(MenuItem).order_by(PlacedOrders.order_date.desc()).all()

    # Group orders by order_id (assuming each order_id is unique per item entry)
    grouped_orders = {}
    for order in orders:
        order_key = order.order_id  # Use order_id as the key
        if order_key not in grouped_orders:
            # Determine status based on order age (simplified logic)
            status = 'Completed' if (datetime.utcnow() - order.order_date) > timedelta(hours=1) else 'In Progress'
            grouped_orders[order_key] = {
                'order_id': order.order_id,
                'customer_name': order.user.name,
                'order_date': order.order_date,
                'order_items': [],  # Changed from 'items' to 'order_items'
                'total': 0.0,
                'status': status
            }
        # Add item details
        grouped_orders[order_key]['order_items'].append({  # Changed to 'order_items'
            'name': order.item.name,
            'quantity': order.quantity,
            'price': order.item.price
        })
        # Update total
        grouped_orders[order_key]['total'] += order.item.price * order.quantity

    # Convert to list for template rendering
    orders_list = list(grouped_orders.values())

    return render_template('restaurant_orders.html', orders=orders_list)

from wtforms import IntegerField, TextAreaField
from wtforms.validators import InputRequired, Length, Email, Regexp, NumberRange 
# Feedback Form
class FeedbackForm(FlaskForm):
    rating = IntegerField('Rating (1-5)', validators=[InputRequired(), NumberRange(min=1, max=5)])
    comment = TextAreaField('Comment', validators=[Length(max=500)])
    submit = SubmitField('Submit Feedback')

@app.route('/view_orders')
@login_required
def view_orders():
    if current_user.role != 'customer':
        flash('Access denied. Customer role required.', 'danger')
        return redirect(url_for('dashboard'))

    # Query all orders for the current user
    orders = PlacedOrders.query.filter_by(user_id=current_user.id).join(MenuItem).order_by(PlacedOrders.order_date.desc()).all()

    # Group orders by order_id
    grouped_orders = {}
    for order in orders:
        order_key = order.order_id
        if order_key not in grouped_orders:
            status = 'Completed' if (datetime.utcnow() - order.order_date) > timedelta(hours=1) else 'In Progress'
            grouped_orders[order_key] = {
                'order_id': order.order_id,
                'order_date': order.order_date,
                'order_items': [],
                'total': 0.0,
                'status': status,
                'has_feedback': Review.query.filter_by(order_id=order.order_id, user_id=current_user.id).first() is not None
            }
        grouped_orders[order_key]['order_items'].append({
            'name': order.item.name,
            'quantity': order.quantity,
            'price': order.item.price
        })
        grouped_orders[order_key]['total'] += order.item.price * order.quantity

    orders_list = list(grouped_orders.values())

    return render_template('view_orders.html', orders=orders_list)

# Submit Feedback Route
@app.route('/submit_feedback/<int:order_id>', methods=['GET', 'POST'])
@login_required
def submit_feedback(order_id):
    if current_user.role != 'customer':
        flash('Access denied. Customer role required.', 'danger')
        return redirect(url_for('dashboard'))

    # Verify the order belongs to the user
    order = PlacedOrders.query.filter_by(order_id=order_id, user_id=current_user.id).first()
    if not order:
        flash('Order not found or you do not have access.', 'danger')
        return redirect(url_for('view_orders'))

    # Check if feedback already exists
    existing_feedback = Review.query.filter_by(order_id=order_id, user_id=current_user.id).first()
    if existing_feedback:
        flash('You have already submitted feedback for this order.', 'warning')
        return redirect(url_for('view_orders'))

    form = FeedbackForm()
    if form.validate_on_submit():
        try:
            feedback = Review(
                user_id=current_user.id,
                order_id=order_id,
                rating=form.rating.data,
                comment=form.comment.data or None
            )
            db.session.add(feedback)
            db.session.commit()
            flash('Feedback submitted successfully!', 'success')
            return redirect(url_for('view_orders'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error submitting feedback: {e}')
            flash('An error occurred while submitting feedback.', 'danger')

    return render_template('feedback.html', form=form, order_id=order_id)
@app.route('/register', methods=['GET', 'POST'])
def register():
    logger.debug("Entering register route")
    form = RegisterForm()
    logger.debug(f'Register form data: {form.data}')
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        new_user = User(
            name=form.name.data,
            email=form.email.data.lower(),  # Normalize email
            phone=form.phone.data,
            password=hashed_password,
            role=form.role.data
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            logger.debug(f'User {new_user.email} saved with ID: {new_user.id}')
            logger.debug(f'Stored password hash: {hashed_password}')
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
    logger.debug("Entering login route")
    form = LoginForm()
    if form.validate_on_submit():
        logger.debug(f"Login form data: {form.email.data}, {form.password.data}")
        user = User.query.filter_by(email=form.email.data.lower()).first()
        logger.debug(f"User lookup for {form.email.data}: {'Found' if user else 'Not found'}")
        if user:
            logger.debug(f"Checking password for {user.email}")
            if bcrypt.check_password_hash(user.password, form.password.data):
                login_user(user)
                logger.debug(f"User {user.email} logged in with role: {user.role}")
                logger.debug(f"Current user ID: {current_user.id if current_user.is_authenticated else 'Not authenticated'}")
                if user.role == 'restaurant':
                    return redirect(url_for('restaurant_dashboard'))
                return redirect(url_for('dashboard'))
            else:
                logger.debug(f"Password mismatch for {user.email}")
                flash('Invalid email or password', 'danger')
        else:
            logger.debug(f"No user found for email: {form.email.data}")
            flash('Invalid email or password', 'danger')
    else:
        logger.debug(f"Form validation failed with errors: {form.errors}")
    return render_template('login.html', form=form)


# Dashboard Route (Protected)
@app.route('/dashboard')
@login_required
def dashboard():
    menu_items = MenuItem.query.all()
    logger.debug(f'User {current_user.email} accessed dashboard')
    # Get unique group_type values
    unique_group_types = db.session.query(MenuItem.group_type).distinct().all()
    group_types = [item[0] for item in unique_group_types]  # Convert tuple to list
    return render_template('dashboard.html', menu_items=menu_items, group_types=group_types)

# ... (other imports and configurations remain unchanged)

# ... (other imports and configurations remain unchanged)
from datetime import timedelta

@app.route('/restaurant_dashboard')
@login_required
def restaurant_dashboard():
    if current_user.role != 'restaurant':
        flash('Access denied. Restaurant role required.', 'danger')
        return redirect(url_for('dashboard'))

    # Query orders
    orders = PlacedOrders.query.join(User).join(MenuItem).order_by(PlacedOrders.order_date.desc()).all()

    # Group orders by order_id for recent orders
    grouped_orders = {}
    for order in orders:
        order_key = order.order_id
        if order_key not in grouped_orders:
            time_diff = datetime.utcnow() - order.order_date
            if time_diff > timedelta(hours=2):
                status = 'Delivered'
                status_class = 'bg-green-100 text-green-800'
            elif time_diff > timedelta(hours=1):
                status = 'Delivering'
                status_class = 'bg-blue-100 text-blue-800'
            else:
                status = 'Preparing'
                status_class = 'bg-yellow-100 text-yellow-800'
            grouped_orders[order_key] = {
                'order_id': order.order_id,
                'customer_name': order.user.name,
                'order_items': [],
                'total': 0.0,
                'status': status,
                'status_class': status_class
            }
        grouped_orders[order_key]['order_items'].append(f"{order.quantity}x {order.item.name}")
        grouped_orders[order_key]['total'] += order.item.price * order.quantity

    # Get recent orders (last 3)
    recent_orders = list(grouped_orders.values())[:3]

    # Calculate summary metrics
    total_orders = len(grouped_orders)
    revenue = sum(order['total'] for order in grouped_orders.values())
    
    # Active orders (Preparing or Delivering)
    active_orders = sum(1 for order in grouped_orders.values() if order['status'] in ['Preparing', 'Delivering'])
    active_breakdown = {
        'preparing': sum(1 for order in grouped_orders.values() if order['status'] == 'Preparing'),
        'delivering': sum(1 for order in grouped_orders.values() if order['status'] == 'Delivering')
    }

    # Average rating from reviews for orders linked to the restaurant
    reviews = (
        Review.query
        .join(PlacedOrders, Review.order_id == PlacedOrders.order_id)
        .join(MenuItem, PlacedOrders.item_id == MenuItem.item_id)
        .filter(MenuItem.restaurant_id == current_user.id)
        .all()
    )
    review_count = len(reviews)
    average_rating = sum(review.rating for review in reviews) / review_count if review_count > 0 else 0.0

    # Mock percentage changes
    orders_change = "+12%"
    revenue_change = "+8%"

    return render_template('restaurant_dashboard.html',
                         total_orders=total_orders,
                         revenue=revenue,
                         average_rating=average_rating,
                         active_orders=active_orders,
                         active_breakdown=active_breakdown,
                         recent_orders=recent_orders,
                         orders_change=orders_change,
                         revenue_change=revenue_change)

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



@app.route('/restaurant_review')
@login_required
def restaurant_review():
    if current_user.role != 'restaurant':
        flash('Access denied. Restaurant role required.', 'danger')
        return redirect(url_for('dashboard'))

    # Query reviews for orders linked to the restaurant's menu items
    reviews = (
        Review.query
        .join(PlacedOrders, Review.order_id == PlacedOrders.order_id)
        .join(MenuItem, PlacedOrders.item_id == MenuItem.item_id)
        .join(User, Review.user_id == User.id)  # Join with User for customer details
        .filter(MenuItem.restaurant_id == current_user.id)  # Filter by restaurant's menu items
        .order_by(Review.review_date.desc())
        .all()
    )

    # Calculate average rating and review count
    review_count = len(reviews)
    average_rating = sum(review.rating for review in reviews) / review_count if review_count > 0 else 0.0

    return render_template('restaurant_review.html', reviews=reviews, average_rating=average_rating, review_count=review_count)
from wtforms import FloatField, IntegerField

class RestaurantSettingsForm(FlaskForm):
    restaurant_name = StringField('Restaurant Name', validators=[InputRequired(), Length(max=100)])
    contact_number = StringField('Contact Number', validators=[
        InputRequired(), Length(min=10, max=15), Regexp(r'^\d+$', message="Phone number must contain only digits.")
    ])
    address = StringField('Address', validators=[InputRequired(), Length(max=255)])
    opening_time = StringField('Opening Time', validators=[InputRequired(), Regexp(r'^\d{2}:\d{2}$', message="Time must be in HH:MM format")])
    closing_time = StringField('Closing Time', validators=[InputRequired(), Regexp(r'^\d{2}:\d{2}$', message="Time must be in HH:MM format")])
    minimum_order_amount = FloatField('Minimum Order Amount', validators=[InputRequired()])
    delivery_radius = IntegerField('Delivery Radius', validators=[InputRequired()])
    submit = SubmitField('Save Changes')

class RestaurantSettings(db.Model):
    __tablename__ = 'restaurant_settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    restaurant_name = db.Column(db.String(100), nullable=False)
    contact_number = db.Column(db.String(15), nullable=False)
    address = db.Column(db.Text, nullable=False)
    opening_time = db.Column(db.String(5), nullable=False)  # e.g., "09:00"
    closing_time = db.Column(db.String(5), nullable=False)  # e.g., "22:00"
    minimum_order_amount = db.Column(db.Float, nullable=False)
    delivery_radius = db.Column(db.Integer, nullable=False)
    user = db.relationship('User', backref='restaurant_settings')

@app.route('/restaurant_additem', methods=['GET', 'POST'])
@login_required
def restaurant_additem():
    if current_user.role != 'restaurant':
        flash('Access denied. Restaurant role required.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name']
        group_type = request.form['group']
        price = float(request.form['price'])
        image = request.form['image']

        new_item = MenuItem(
            name=name,
            group_type=group_type,
            price=price,
            image=image,
            restaurant_id=current_user.id
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Menu item added successfully!', 'success')

    menu_items = MenuItem.query.filter_by(restaurant_id=current_user.id).all()
    return render_template('restaurant_additem.html', menu_items=menu_items)

@app.route('/restaurant_edititem/<int:item_id>', methods=['GET', 'POST'])
@login_required
def restaurant_edititem(item_id):
    if current_user.role != 'restaurant':
        flash('Access denied. Restaurant role required.', 'danger')
        return redirect(url_for('dashboard'))

    item = MenuItem.query.filter_by(item_id=item_id, restaurant_id=current_user.id).first_or_404()

    if request.method == 'POST':
        item.name = request.form['name']
        item.group_type = request.form['group']
        item.price = float(request.form['price'])
        item.image = request.form['image']
        db.session.commit()
        flash('Menu item updated successfully!', 'success')
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

@app.route('/restaurant_settings', methods=['GET', 'POST'])
@login_required
def restaurant_settings():
    if current_user.role != 'restaurant':
        flash('Access denied. Restaurant role required.', 'danger')
        return redirect(url_for('dashboard'))
    
    form = RestaurantSettingsForm()
    settings = RestaurantSettings.query.filter_by(user_id=current_user.id).first()
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            if settings:
                # Update existing settings
                settings.restaurant_name = form.restaurant_name.data
                settings.contact_number = form.contact_number.data
                settings.address = form.address.data
                settings.opening_time = form.opening_time.data
                settings.closing_time = form.closing_time.data
                settings.minimum_order_amount = form.minimum_order_amount.data
                settings.delivery_radius = form.delivery_radius.data
            else:   
                # Create new settings
                new_settings = RestaurantSettings(
                    user_id=current_user.id,
                    restaurant_name=form.restaurant_name.data,
                    contact_number=form.contact_number.data,
                    address=form.address.data,
                    opening_time=form.opening_time.data,
                    closing_time=form.closing_time.data,
                    minimum_order_amount=form.minimum_order_amount.data,
                    delivery_radius=form.delivery_radius.data
                )
                db.session.add(new_settings)
            db.session.commit()
            flash('Settings saved successfully!', 'success')
            return redirect(url_for('restaurant_settings'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error saving restaurant settings: {e}')
            flash('An error occurred while saving settings.', 'danger')
    
    # Populate form with existing settings for GET request
    if settings:
        form.restaurant_name.data = settings.restaurant_name
        form.contact_number.data = settings.contact_number
        form.address.data = settings.address
        form.opening_time.data = settings.opening_time
        form.closing_time.data = settings.closing_time
        form.minimum_order_amount.data = settings.minimum_order_amount
        form.delivery_radius.data = settings.delivery_radius
    
    return render_template('restaurant_settings.html', form=form)

@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    # Assuming user is authenticated and user_id is in session
    if 'user_id' not in session:
        flash('Please log in to confirm payment.', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    # Retrieve cart items for the user
    cart_items = Cart.query.filter_by(user_id=user_id).all()
    
    if not cart_items:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('cart'))

    try:
        # Add cart items to placed_orders
        for cart_item in cart_items:
            item = Item.query.get(cart_item.item_id)
            if item:
                total_amount = item.price * cart_item.quantity
                order = PlacedOrder(
                    user_id=user_id,
                    item_id=cart_item.item_id,
                    quantity=cart_item.quantity,
                    total_amount=total_amount
                )
                db.session.add(order)
        
        # Commit the orders to the database
        db.session.commit()
        
        # Remove items from cart
        Cart.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        
        flash('Order placed successfully!', 'success')
        return redirect(url_for('delivery_tracking'))
    
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while processing your order. Please try again.', 'error')
        return redirect(url_for('cart'))


@app.route('/remove_from_cart/<int:cart_id>', methods=['POST'])
@login_required
def remove_from_cart(cart_id):
    try:
        # Find the cart item by cart_id and ensure it belongs to the current user
        cart_item = Cart.query.filter_by(cart_id=cart_id, id=current_user.id).first_or_404()
        
        # Delete the cart item
        db.session.delete(cart_item)
        db.session.commit()
        
        flash('Item removed from cart successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error removing cart item: {e}')
        flash('An error occurred while removing the item.', 'danger')
    
    return redirect(url_for('cart'))

# Create Database Tables if They Don't Exist
if __name__ == '__main__':
    if not os.path.exists("users.db"):
        with app.app_context():
            db.create_all()
            logger.info('Database initialized successfully!')
    logger.info('Starting Flask application...')
    app.run(debug=True) 
