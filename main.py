import logging
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
import threading

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Mock exchange API integrations
EXCHANGES = {
    'OKX': {'base_url': 'https://www.okx.com/api/v5/'},
    'Bybit': {'base_url': 'https://api.bybit.com/'},
    'Deribit': {'base_url': 'https://www.deribit.com/api/v2/'}
}

# Risk thresholds configuration
RISK_THRESHOLDS = {
    'delta': 0.1,       # 10% delta exposure
    'var': 0.05,       # 5% VaR
    'gamma': 0.2,
    'theta': 0.15,
    'vega': 0.25
}

class HedgingBot:
    def __init__(self, telegram_token):
        self.updater = Updater(token=telegram_token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.active_monitors = {}
        self.positions = {}
        self.risk_metrics = {}
        
        # Register handlers
        self.dispatcher.add_handler(CommandHandler('start', self.start))
        self.dispatcher.add_handler(CommandHandler('monitor_risk', self.monitor_risk, pass_args=True))
        self.dispatcher.add_handler(CommandHandler('auto_hedge', self.auto_hedge, pass_args=True))
        self.dispatcher.add_handler(CommandHandler('hedge_status', self.hedge_status))
        self.dispatcher.add_handler(CommandHandler('hedge_history', self.hedge_history))
        self.dispatcher.add_handler(CommandHandler('hedge_now', self.hedge_now, pass_args=True))
        self.dispatcher.add_handler(CommandHandler('stop_monitoring', self.stop_monitoring))
        self.dispatcher.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Start risk monitoring thread
        self.monitoring_thread = threading.Thread(target=self.run_risk_monitoring)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    def start(self, update, context):
        """Send welcome message when the command /start is issued."""
        welcome_text = """
  *GoQuant Spot Exposure Hedging Bot*

This bot helps you manage risk exposure from spot positions by automatically hedging with perpetual futures or options.

*Available Commands:*
/monitor_risk [asset] [position_size] [risk_threshold] - Start monitoring risk for a position
/auto_hedge [strategy] [threshold] - Configure automated hedging
/hedge_status - View current hedging status
/hedge_history [asset] [timeframe] - View hedging performance history
/hedge_now [asset] [size] - Manually trigger hedging
/stop_monitoring - Stop all risk monitoring

Example: `/monitor_risk BTC 1.5 0.1` to monitor 1.5 BTC position with 10% delta threshold
"""
        update.message.reply_text(welcome_text, parse_mode='Markdown')

    def monitor_risk(self, update, context):
        """Start monitoring risk for a specific position."""
        try:
            args = context.args
            if len(args) != 3:
                update.message.reply_text('Usage: /monitor_risk [asset] [position_size] [risk_threshold]')
                return
            
            asset = args[0].upper()
            position_size = float(args[1])
            risk_threshold = float(args[2])
            
            chat_id = update.message.chat_id
            self.active_monitors[chat_id] = {
                'asset': asset,
                'position_size': position_size,
                'risk_threshold': risk_threshold,
                'last_alert': None,
                'hedge_status': 'not_hedged'
            }
            
            self.positions[asset] = position_size
            
            update.message.reply_text(
                f" Started risk monitoring for {asset} position of {position_size} "
                f"with {risk_threshold*100}% risk threshold"
            )
            
        except Exception as e:
            update.message.reply_text(f"❌ Error: {str(e)}")

    def auto_hedge(self, update, context):
        """Configure automated hedging strategy."""
        try:
            args = context.args
            if len(args) < 2:
                update.message.reply_text('Usage: /auto_hedge [strategy] [threshold]')
                return
                
            strategy = args[0].lower()
            threshold = float(args[1])
            
            valid_strategies = ['delta_neutral', 'protective_puts', 'covered_calls', 'dynamic']
            if strategy not in valid_strategies:
                update.message.reply_text(f"Invalid strategy. Choose from {', '.join(valid_strategies)}")
                return
                
            chat_id = update.message.chat_id
            if chat_id not in self.active_monitors:
                update.message.reply_text("Please start risk monitoring first with /monitor_risk")
                return
                
            self.active_monitors[chat_id]['hedge_strategy'] = strategy
            self.active_monitors[chat_id]['hedge_threshold'] = threshold
            
            keyboard = [
                [InlineKeyboardButton("Hedge Now", callback_data='hedge_now')],
                [InlineKeyboardButton("Adjust Threshold", callback_data='adjust_threshold')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                f" Configured {strategy.replace('_', ' ')} strategy with {threshold*100}% threshold",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            update.message.reply_text(f"❌ Error: {str(e)}")

    def hedge_status(self, update, context):
        """View current hedging status."""
        try:
            chat_id = update.message.chat_id
            if chat_id not in self.active_monitors:
                update.message.reply_text("No active monitoring. Use /monitor_risk first.")
                return
                
            monitor = self.active_monitors[chat_id]
            asset = monitor['asset']
            position_size = monitor['position_size']
            risk_threshold = monitor['risk_threshold']
            hedge_status = monitor.get('hedge_status', 'not_hedged')
            
            status_text = f"""
   *Hedging Status for {asset}*

- Position Size: {position_size}
- Current Risk Threshold: {risk_threshold*100}%
- Hedge Status: {hedge_status.replace('_', ' ').title()}
- Last Calculated Delta: {self.risk_metrics.get(asset, {}).get('delta', 0):.4f}
- Portfolio VaR: {self.risk_metrics.get(asset, {}).get('var', 0):.4f}
"""
            update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            update.message.reply_text(f"❌ Error: {str(e)}")

    def hedge_now(self, update, context):
        """Manually trigger hedging."""
        try:
            args = context.args
            if len(args) != 2:
                update.message.reply_text('Usage: /hedge_now [asset] [size]')
                return
                
            asset = args[0].upper()
            size = float(args[1])
            
            # Here you would normally place the hedge order
            # For demo purposes we'll just simulate it
            
            self.active_monitors[update.message.chat_id]['hedge_status'] = f'hedged_{size}'
            
            update.message.reply_text(
                f" Successfully hedged {size} of {asset} exposure"
                "\n\nCalculated optimal execution across exchanges with minimal slippage."
            )
            
            # Simulate order execution
            execution_details = {
                'size': size,
                'price': self.get_market_price(asset),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'filled'
            }
            
            self.save_hedge_history(asset, execution_details)
            
        except Exception as e:
            update.message.reply_text(f" Error: {str(e)}")

    def hedge_history(self, update, context):
        """View hedging performance history."""
        try:
            args = context.args
            if len(args) != 2:
                update.message.reply_text('Usage: /hedge_history [asset] [timeframe]')
                return
                
            asset = args[0].upper()
            timeframe = args[1]
            
            # For demo we'll return some mock data
            history_text = f"""
📜 *Hedging History for {asset} ({timeframe})*

- Total Hedges: 5
- Avg Hedge Size: 0.8
- Avg Execution Price: $61,250
- Total Cost: $245 (0.08%)
+ Performance Impact: -1.2% (vs unhedged)

Last 3 hedges:
1. 2023-11-15 | Size: 0.75 | Price: $61,100 | Cost: 0.07%
2. 2023-11-14 | Size: 0.85 | Price: $60,950 | Cost: 0.08%
3. 2023-11-13 | Size: 0.80 | Price: $61,300 | Cost: 0.09%
"""
            update.message.reply_text(history_text, parse_mode='Markdown')
            
        except Exception as e:
            update.message.reply_text(f" Error: {str(e)}")

    def stop_monitoring(self, update, context):
        """Stop all risk monitoring."""
        chat_id = update.message.chat_id
        if chat_id in self.active_monitors:
            asset = self.active_monitors[chat_id]['asset']
            del self.active_monitors[chat_id]
            update.message.reply_text(f"⏹ Stopped risk monitoring for {asset}")
        else:
            update.message.reply_text("No active monitoring to stop")

    def button_handler(self, update, context):
        """Handle inline button presses."""
        query = update.callback_query
        query.answer()
        
        chat_id = query.message.chat_id
        if chat_id not in self.active_monitors:
            query.edit_message_text(text="Session expired. Start new monitoring with /monitor_risk")
            return
            
        if query.data == 'hedge_now':
            asset = self.active_monitors[chat_id]['asset']
            size = self.calculate_optimal_hedge(asset)
            query.edit_message_text(
                text=f"💱 Hedge {size} of {asset}?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Confirm", callback_data='confirm_hedge')],
                    [InlineKeyboardButton("Cancel", callback_data='cancel')]
                ])
            )
            
        elif query.data == 'confirm_hedge':
            asset = self.active_monitors[chat_id]['asset']
            size = self.calculate_optimal_hedge(asset)
            self.active_monitors[chat_id]['hedge_status'] = f'hedged_{size}'
            
            # Simulate execution
            execution_details = {
                'size': size,
                'price': self.get_market_price(asset),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'filled'
            }
            self.save_hedge_history(asset, execution_details)
            
            query.edit_message_text(
                text=f" Successfully hedged {size} of {asset} at ${execution_details['price']:,}"
            )
            
        elif query.data == 'adjust_threshold':
            query.edit_message_text(
                text="Enter new risk threshold (0-1):",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("0.05 (5%)", callback_data='threshold_0.05')],
                    [InlineKeyboardButton("0.10 (10%)", callback_data='threshold_0.10')],
                    [InlineKeyboardButton("0.15 (15%)", callback_data='threshold_0.15')],
                    [InlineKeyboardButton("Custom", callback_data='threshold_custom')]
                ])
            )
            
        elif query.data.startswith('threshold_'):
            if query.data == 'threshold_custom':
                query.edit_message_text(text="Please send your custom threshold (e.g. '0.12')")
            else:
                threshold = float(query.data.split('_')[1])
                self.active_monitors[chat_id]['risk_threshold'] = threshold
                query.edit_message_text(text=f" Risk threshold updated to {threshold*100:.0f}%")

    def run_risk_monitoring(self):
        """Continuous risk monitoring thread."""
        while True:
            try:
                for chat_id, monitor in list(self.active_monitors.items()):
                    asset = monitor['asset']
                    position_size = monitor['position_size']
                    risk_threshold = monitor['risk_threshold']
                    
                    # Calculate risk metrics
                    risk_metrics = self.calculate_risk_metrics(asset, position_size)
                    self.risk_metrics[asset] = risk_metrics
                    
                    # Check if we need to alert
                    delta_exposure = abs(risk_metrics['delta'])
                    should_alert = (
                        delta_exposure > risk_threshold or
                        risk_metrics['var'] > RISK_THRESHOLDS['var']
                    )
                    
                    if should_alert and (
                        monitor.get('last_alert') is None or 
                        (datetime.now() - monitor['last_alert']).seconds > 300  # 5 min cooldown
                    ):
                        self.send_risk_alert(chat_id, asset, risk_metrics)
                        monitor['last_alert'] = datetime.now()
                        
                        # If auto hedge is configured and threshold exceeded, hedge automatically
                        if monitor.get('hedge_strategy') and delta_exposure > monitor.get('hedge_threshold', 1.0):
                            hedge_size = self.calculate_optimal_hedge(asset)
                            self.execute_hedge(asset, hedge_size)
                            monitor['hedge_status'] = f'hedged_{hedge_size}'
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in risk monitoring thread: {str(e)}")
                time.sleep(30)

    def send_risk_alert(self, chat_id, asset, risk_metrics):
        """Send a risk alert to Telegram."""
        delta_exposure = risk_metrics['delta']
        var = risk_metrics['var']
        recommended_hedge = self.calculate_optimal_hedge(asset)
        
        alert_text = f"""
🚨 *Risk Alert for {asset}*

- Delta Exposure: {delta_exposure:.2%}
- Portfolio VaR: {var:.2%}
- Recommended Hedge: {recommended_hedge}

*Market Conditions:*
- Current Price: ${risk_metrics['price']:,.2f}
- 24h Volatility: {risk_metrics['volatility']:.2%}
- Liquidity Score: {risk_metrics['liquidity']}/100
"""
        keyboard = [
            [InlineKeyboardButton("Hedge Now", callback_data='hedge_now')],
            [
                InlineKeyboardButton("Adjust Threshold", callback_data='adjust_threshold'),
                InlineKeyboardButton("View Analytics", callback_data='view_analytics')
            ]
        ]
        self.updater.bot.send_message(
            chat_id=chat_id,
            text=alert_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def calculate_risk_metrics(self, asset, position_size):
        """Calculate various risk metrics for a position."""
        try:
            price = self.get_market_price(asset)
            volatility = self.get_volatility(asset)
            liquidity = self.get_liquidity_score(asset)
            
            # Mock calculations (in a real implementation these would be proper models)
            delta = np.random.uniform(-0.2, 0.2)  # Random delta for demo
            gamma = np.random.uniform(0.01, 0.05)
            theta = np.random.uniform(-0.001, 0.001)
            vega = np.random.uniform(0.005, 0.015)
            var = min(0.2, max(0.01, delta * position_size * 0.5))
            
            return {
                'delta': delta,
                'gamma': gamma,
                'theta': theta,
                'vega': vega,
                'var': var,
                'price': price,
                'volatility': volatility,
                'liquidity': liquidity
            }
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {str(e)}")
            return {}

    def calculate_optimal_hedge(self, asset):
        """Calculate optimal hedge size based on current risk."""
        try:
            risk_metrics = self.risk_metrics.get(asset, {})
            delta = risk_metrics.get('delta', 0)
            position_size = self.positions.get(asset, 0)
            
            if delta == 0 or position_size == 0:
                return 0
                
            # Simple calculation - in reality this would be more sophisticated
            hedge_ratio = abs(delta) * 1.0  # Neutral ratio
            return position_size * hedge_ratio
            
        except Exception as e:
            logger.error(f"Error calculating optimal hedge: {str(e)}")
            return 0

    def execute_hedge(self, asset, size):
        """Execute hedge order (mock implementation)."""
        logger.info(f"Executing hedge order for {asset}: size={size}")
        # In a real implementation this would place actual orders
        
        execution_details = {
            'asset': asset,
            'size': size,
            'price': self.get_market_price(asset),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'filled'
        }
        self.save_hedge_history(asset, execution_details)
        return execution_details

    def get_market_price(self, asset):
        """Get current market price for an asset."""
        # Mock implementation - would use exchange API in production
        prices = {
            'BTC': 62000 + np.random.uniform(-500, 500),
            'ETH': 3400 + np.random.uniform(-50, 50),
            'SOL': 120 + np.random.uniform(-2, 2)
        }
        return prices.get(asset, 0)

    def get_volatility(self, asset):
        """Get volatility estimate for an asset."""
        # Mock implementation
        return np.random.uniform(0.01, 0.05)

    def get_liquidity_score(self, asset):
        """Get liquidity score for an asset."""
        # Mock implementation
        return int(np.random.uniform(80, 95))

    def save_hedge_history(self, asset, details):
        """Save hedge execution details."""
        # In a real implementation this would persist to database
        logger.info(f"Hedge executed: {asset} {details}")

def main():
    """Start the bot."""
    # Replace with your actual Telegram bot token
    TOKEN = '7767232091:AAGCGbrF4_vXUZARQ4SlE6J4K9RNYAspTR8'
    
    bot = HedgingBot(TOKEN)
    logger.info("Hedging bot started")
    bot.updater.start_polling()
    bot.updater.idle()

if __name__ == '__main__':
    main()

